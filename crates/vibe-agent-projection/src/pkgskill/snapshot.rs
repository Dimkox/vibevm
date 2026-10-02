//! No-follow skill snapshots, include filtering, and destination writes.

specmark::scope!("spec://org.vibevm.core/vibevm/common/PROP-018#vibe-skill");

use super::*;

/// Snapshot a skill body source into a `relpath -> bytes` map. A directory
/// is walked recursively (relpaths forward-slashed); a single file maps to
/// its file name (so a bare `SKILL.md` source lands as `<name>/SKILL.md`).
///
/// The **complete selected set** — after `include` filtering — is judged
/// through the shared portability law before it can be returned to any
/// caller, so neither surface ever stages, publishes, or writes a selection
/// carrying a non-storeable spelling or two spellings of one physical file.
pub(super) fn snapshot_source(
    source: &Path,
    include: &[String],
) -> Result<BTreeMap<String, Vec<u8>>, PackageSkillError> {
    let mut out = BTreeMap::new();
    let metadata =
        fs::symlink_metadata(source).map_err(|source_error| PackageSkillError::Read {
            path: source.to_path_buf(),
            source: source_error,
        })?;
    if metadata.file_type().is_symlink() || metadata_is_reparse(&metadata) {
        return Err(PackageSkillError::UnsafePath {
            path: source.to_path_buf(),
            reason: "skill source is a symlink/junction/reparse point".into(),
        });
    }
    if metadata.is_dir() {
        collect_dir(source, source, &mut out)?;
        // PROP-015 §2.8: when `include` is set, keep only the files whose
        // relpath matches one of the patterns. Empty `include` keeps the
        // whole tree (the §2.6 default).
        if !include.is_empty() {
            out.retain(|rel, _| include.iter().any(|pat| glob_match(pat, rel)));
        }
    } else if metadata.is_file() {
        let name = match source.file_name() {
            Some(name) => exact_path::exact_utf8_component(name, source)?,
            None => "SKILL.md".to_string(),
        };
        let bytes = fs::read(source).map_err(|err| PackageSkillError::Read {
            path: source.to_path_buf(),
            source: err,
        })?;
        out.insert(name, bytes);
    } else {
        return Err(PackageSkillError::UnsafePath {
            path: source.to_path_buf(),
            reason: "skill source is neither a regular file nor a directory".into(),
        });
    }
    if let Err(fault) = receipt::judge_selection(out.keys().map(String::as_str)) {
        return Err(PackageSkillError::UnsafePath {
            path: source.to_path_buf(),
            reason: format!("selected source file set is not portable: {fault}"),
        });
    }
    Ok(out)
}

/// Snapshot an existing target dir, or `None` when it does not exist.
pub(super) fn snapshot_dir(
    dir: &Path,
) -> Result<Option<BTreeMap<String, Vec<u8>>>, PackageSkillError> {
    let metadata = match fs::symlink_metadata(dir) {
        Ok(metadata) => metadata,
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(None),
        Err(source) => {
            return Err(PackageSkillError::Read {
                path: dir.to_path_buf(),
                source,
            });
        }
    };
    if metadata.file_type().is_symlink() || metadata_is_reparse(&metadata) || !metadata.is_dir() {
        return Err(PackageSkillError::UnsafePath {
            path: dir.to_path_buf(),
            reason: "skill target is not a no-follow directory".into(),
        });
    }
    let mut out = BTreeMap::new();
    collect_dir(dir, dir, &mut out)?;
    Ok(Some(out))
}

pub(super) fn collect_dir(
    base: &Path,
    dir: &Path,
    out: &mut BTreeMap<String, Vec<u8>>,
) -> Result<(), PackageSkillError> {
    let entries = fs::read_dir(dir).map_err(|source| PackageSkillError::Read {
        path: dir.to_path_buf(),
        source,
    })?;
    for entry in entries {
        let entry = entry.map_err(|source| PackageSkillError::Read {
            path: dir.to_path_buf(),
            source,
        })?;
        let path = entry.path();
        let metadata = fs::symlink_metadata(&path).map_err(|source| PackageSkillError::Read {
            path: path.clone(),
            source,
        })?;
        if metadata.file_type().is_symlink() || metadata_is_reparse(&metadata) {
            return Err(PackageSkillError::UnsafePath {
                path,
                reason: "skill tree contains a symlink/junction/reparse point".into(),
            });
        }
        if metadata.is_dir() {
            collect_dir(base, &path, out)?;
        } else if metadata.is_file() {
            let rel = exact_path::exact_utf8_relative(base, &path)?;
            let bytes = fs::read(&path).map_err(|source| PackageSkillError::Read {
                path: path.clone(),
                source,
            })?;
            // Two entries can only ever land on one key through a lossy
            // rendering, which no longer exists; refuse rather than let one
            // file's bytes silently replace another's.
            if out.insert(rel.clone(), bytes).is_some() {
                return Err(PackageSkillError::UnsafePath {
                    path,
                    reason: format!("two skill tree entries share the relative path `{rel}`"),
                });
            }
        } else {
            return Err(PackageSkillError::UnsafePath {
                path,
                reason: "skill tree contains a non-file, non-directory entry".into(),
            });
        }
    }
    Ok(())
}

/// Match a forward-slash relpath against a restricted glob (PROP-015 §2.8):
/// `*` matches a run of non-`/` chars, `**` matches across `/`, `?` one
/// non-`/` char; everything else is literal, and a trailing `/` selects a
/// whole subtree. Deterministic; filters a skill's projected files.
pub(super) fn glob_match(pattern: &str, path: &str) -> bool {
    if let Some(prefix) = pattern.strip_suffix('/') {
        return path == prefix || path.starts_with(&format!("{prefix}/"));
    }
    glob_rec(pattern.as_bytes(), path.as_bytes())
}

pub(super) fn glob_rec(p: &[u8], t: &[u8]) -> bool {
    if p.is_empty() {
        return t.is_empty();
    }
    if let Some(rest) = p.strip_prefix(b"**") {
        // `**` spans path separators; an optional following `/` is folded
        // in so `**/x` also matches a top-level `x`.
        let rest = rest.strip_prefix(b"/").unwrap_or(rest);
        if glob_rec(rest, t) {
            return true;
        }
        for i in 0..t.len() {
            if glob_rec(rest, &t[i + 1..]) {
                return true;
            }
        }
        return false;
    }
    match p[0] {
        b'*' => {
            // A single `*` stays within one path segment.
            if glob_rec(&p[1..], t) {
                return true;
            }
            let mut i = 0;
            while i < t.len() && t[i] != b'/' {
                i += 1;
                if glob_rec(&p[1..], &t[i..]) {
                    return true;
                }
            }
            false
        }
        b'?' => !t.is_empty() && t[0] != b'/' && glob_rec(&p[1..], &t[1..]),
        c => !t.is_empty() && t[0] == c && glob_rec(&p[1..], &t[1..]),
    }
}

pub(super) fn write_snapshot(
    target_dir: &Path,
    snap: &BTreeMap<String, Vec<u8>>,
) -> Result<(), PackageSkillError> {
    fs::create_dir_all(target_dir).map_err(|source| PackageSkillError::Write {
        path: target_dir.to_path_buf(),
        source,
    })?;
    for (rel, bytes) in snap {
        let dest = target_dir.join(rel);
        if let Some(parent) = dest.parent() {
            fs::create_dir_all(parent).map_err(|source| PackageSkillError::Write {
                path: parent.to_path_buf(),
                source,
            })?;
        }
        fs::write(&dest, bytes).map_err(|source| PackageSkillError::Write {
            path: dest.clone(),
            source,
        })?;
    }
    Ok(())
}
