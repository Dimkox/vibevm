//! Transactional publication of owned application files.

specmark::scope!("spec://org.vibevm.core/vibevm/common/PROP-059#distribution");

use anyhow::{Context, Result, bail};
use std::fs;
use std::path::{Path, PathBuf};

pub(super) struct PublishedFiles {
    backups: Vec<(PathBuf, PathBuf)>,
    published: Vec<PathBuf>,
}

impl PublishedFiles {
    pub(super) fn commit(self) {
        for (backup, _) in self.backups {
            let _ = fs::remove_file(backup);
        }
    }

    pub(super) fn rollback(self) -> Result<()> {
        for destination in self.published.iter().rev() {
            match fs::remove_file(destination) {
                Ok(()) => {}
                Err(error) if error.kind() == std::io::ErrorKind::NotFound => {}
                Err(error) => return Err(error).context("removing rolled-back application file"),
            }
        }
        for (backup, destination) in self.backups.into_iter().rev() {
            fs::rename(&backup, &destination).context("restoring prior application file")?;
        }
        Ok(())
    }
}

pub(super) fn publish_files(
    desired: &[(PathBuf, PathBuf)],
    retire: &[PathBuf],
) -> Result<PublishedFiles> {
    let mut destinations = std::collections::BTreeSet::new();
    if desired
        .iter()
        .any(|(_, destination)| !destinations.insert(destination.to_path_buf()))
    {
        bail!("application publication repeats a destination");
    }
    for destination in retire {
        if !destinations.insert(destination.clone()) {
            bail!("application publication both replaces and retires a destination");
        }
    }
    let mut staged = Vec::new();
    for (index, (source, destination)) in desired.iter().enumerate() {
        let temporary = sibling_temporary(destination, "pending", index)?;
        fs::copy(source, &temporary)
            .with_context(|| format!("staging launcher `{}`", destination.display()))?;
        staged.push((temporary, destination.clone()));
    }
    let mut backups = Vec::new();
    let mut published = Vec::new();
    let result = (|| {
        for (index, destination) in retire.iter().enumerate() {
            let backup = sibling_temporary(destination, "prior", desired.len() + index)?;
            fs::rename(destination, &backup)?;
            backups.push((backup, destination.clone()));
        }
        for (index, (temporary, destination)) in staged.iter().enumerate() {
            let backup = sibling_temporary(destination, "prior", index)?;
            if destination.exists() {
                fs::rename(destination, &backup)?;
                backups.push((backup, destination.clone()));
            }
            fs::rename(temporary, destination)?;
            published.push(destination.clone());
        }
        Ok::<(), anyhow::Error>(())
    })();
    if let Err(error) = result {
        for destination in published.iter().rev() {
            let _ = fs::remove_file(destination);
        }
        for (backup, destination) in backups.iter().rev() {
            let _ = fs::rename(backup, destination);
        }
        for (temporary, _) in &staged {
            let _ = fs::remove_file(temporary);
        }
        return Err(error).context("publishing application files");
    }
    Ok(PublishedFiles { backups, published })
}

fn sibling_temporary(destination: &Path, role: &str, index: usize) -> Result<PathBuf> {
    let name = destination
        .file_name()
        .and_then(|value| value.to_str())
        .ok_or_else(|| anyhow::anyhow!("application destination has no portable file name"))?;
    Ok(destination.with_file_name(format!("{name}.vibe-{role}-{}-{index}", std::process::id())))
}
