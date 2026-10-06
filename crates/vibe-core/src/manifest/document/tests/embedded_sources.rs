//! Reference-bridge source and composed skill manifest contracts.

use super::*;

const REFERENCE_COMMIT: &str = "0123456789abcdef0123456789abcdef01234567";

fn reference_bridge_manifest(skill_tail: &str) -> String {
    format!(
        r#"
[package]
group = "org.example"
name = "upstream-skill"
kind = "tool"
version = "1.0.0"
bridge = true
license = "UPL-1.0"
authors = ["Bridge Package Maintainer"]

[[embedded_source]]
name = "upstream"
kind = "git"
url = "https://github.com/example/upstream.git"
commit = "{REFERENCE_COMMIT}"
content_hash = "sha256-tree/1:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
ref_hint = "refs/tags/v1.2.3"
auth = "none"
upstream_authors = ["Example Upstream Authors"]
upstream_license = "MIT"
license_path = "LICENSE"
license_url = "https://github.com/example/upstream/blob/{REFERENCE_COMMIT}/LICENSE"

{skill_tail}
"#
    )
}

#[test]
fn reference_bridge_sources_and_skill_inputs_round_trip() {
    let raw = reference_bridge_manifest(
        r#"
[[skill]]
name = "adapter"
path = "skills/adapter"
include = ["SKILL.md"]

[[skill.resource]]
embedded_source = "upstream"
path = "docs"
include = ["guide.md", "examples/**/*.md"]
target = "references/upstream"

[[skill]]
name = "direct-upstream"
source = "upstream"
path = "skills/direct-upstream"
include = ["SKILL.md", "references/**/*.md"]
"#,
    );
    let manifest = Manifest::parse_str(&raw).unwrap();
    assert_eq!(manifest.embedded_sources.len(), 1);
    assert_eq!(manifest.embedded_sources[0].name, "upstream");
    assert_eq!(
        manifest.package.as_ref().unwrap().authors,
        ["Bridge Package Maintainer"]
    );
    assert_eq!(
        manifest.embedded_sources[0].upstream_authors,
        ["Example Upstream Authors"]
    );
    assert_eq!(manifest.skills.len(), 2);
    assert!(manifest.skills[0].source.is_none());
    assert_eq!(manifest.skills[0].resources.len(), 1);
    assert_eq!(manifest.skills[1].source.as_deref(), Some("upstream"));

    let rendered = toml::to_string_pretty(&manifest).unwrap();
    assert!(rendered.contains("[[embedded_source]]"), "{rendered}");
    assert!(rendered.contains("[[skill.resource]]"), "{rendered}");
    let back = Manifest::parse_str(&rendered).unwrap();
    assert_eq!(manifest, back);
}

#[test]
fn embedded_sources_are_package_only_and_unique() {
    let package_source = format!(
        r#"
[[embedded_source]]
name = "upstream"
kind = "git"
url = "https://github.com/example/upstream.git"
commit = "{REFERENCE_COMMIT}"
content_hash = "sha256-tree/1:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
upstream_authors = ["Example Upstream Authors"]
upstream_license = "MIT"
license_path = "LICENSE"
license_url = "https://github.com/example/upstream/blob/{REFERENCE_COMMIT}/LICENSE"
"#
    );
    let project = format!("[project]\nname = \"demo\"\nversion = \"1.0.0\"\n{package_source}");
    let error = Manifest::parse_str(&project).unwrap_err().to_string();
    assert!(error.contains("[[embedded_source]]"), "{error}");
    assert!(error.contains("without a [package]"), "{error}");

    let duplicate = reference_bridge_manifest(&package_source);
    let error = Manifest::parse_str(&duplicate).unwrap_err().to_string();
    assert!(
        error.contains("duplicate [[embedded_source]] name"),
        "{error}"
    );
}

#[test]
fn embedded_source_wire_rejects_mutable_or_credentialed_identity() {
    let valid = reference_bridge_manifest("");
    let without_upstream_authors =
        valid.replace("upstream_authors = [\"Example Upstream Authors\"]\n", "");
    let error = Manifest::parse_str(&without_upstream_authors)
        .unwrap_err()
        .to_string();
    assert!(error.contains("upstream_authors"), "{error}");

    for invalid_authors in ["[]", "[\" leading\"]", "[\"line\\nbreak\"]"] {
        let invalid = valid.replace("[\"Example Upstream Authors\"]", invalid_authors);
        let error = Manifest::parse_str(&invalid).unwrap_err().to_string();
        assert!(error.contains("upstream_authors"), "{error}");
    }

    for (from, to, needle) in [
        (
            "https://github.com/example/upstream.git",
            "http://github.com/example/upstream.git",
            "credential-free HTTPS",
        ),
        (
            "https://github.com/example/upstream.git",
            "https://token@github.com/example/upstream.git",
            "credential-free HTTPS",
        ),
        (
            REFERENCE_COMMIT,
            "0123456789abcdef",
            "full 40- or 64-character",
        ),
        ("refs/tags/v1.2.3", "v1.2.3", "full safe `refs/...`"),
    ] {
        let error = Manifest::parse_str(&valid.replacen(from, to, 1))
            .unwrap_err()
            .to_string();
        assert!(error.contains(needle), "wanted {needle:?}: {error}");
    }

    let error = Manifest::parse_str(&valid.replace("kind = \"git\"", "kind = \"tar\""))
        .unwrap_err()
        .to_string();
    assert!(error.contains("unknown variant"), "{error}");
    let error = Manifest::parse_str(&valid.replace("auth = \"none\"", "auth = \"token\""))
        .unwrap_err()
        .to_string();
    assert!(error.contains("unknown variant"), "{error}");
}

#[test]
fn skill_external_inputs_require_declared_sources_and_safe_selection() {
    let undeclared = reference_bridge_manifest(
        r#"
[[skill]]
name = "direct"
source = "missing"
path = "skills/direct"
include = ["SKILL.md"]
"#,
    );
    let error = Manifest::parse_str(&undeclared).unwrap_err().to_string();
    assert!(
        error.contains("undeclared [[embedded_source]] `missing`"),
        "{error}"
    );

    let no_include = reference_bridge_manifest(
        r#"
[[skill]]
name = "direct"
source = "upstream"
path = "skills/direct"
"#,
    );
    let error = Manifest::parse_str(&no_include).unwrap_err().to_string();
    assert!(error.contains("non-empty include"), "{error}");

    let unsafe_target = reference_bridge_manifest(
        r#"
[[skill]]
name = "adapter"
path = "skills/adapter"

[[skill.resource]]
embedded_source = "upstream"
path = "docs"
include = ["**/*.md"]
target = "SKILL.md"
"#,
    );
    let error = Manifest::parse_str(&unsafe_target).unwrap_err().to_string();
    assert!(error.contains("below `references/`"), "{error}");
}
