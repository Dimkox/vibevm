//! Tests for [`any_package_source`] — the builder's "nothing can serve"
//! question asked on its own — and for the two bails that answer it in
//! words. Split from `flag_tests.rs` so neither file crosses the per-file
//! budget (GUIDE-AI-NATIVE-RUST §2); the fixtures both files need stay
//! defined once, in `flag_tests.rs`, and are read from here.

// Test code, reached through `#[cfg(test)] #[path]` in `builder.rs`.

use std::path::Path;

use vibe_core::GlobalRegistryConfig;
use vibe_core::manifest::Manifest;
use vibe_test_support as _;

use super::flag_tests::{empty_manifest, temp_project_with_packages, write_registry_package};
use super::*;

/// Both "nothing can serve" bails name the project-local registry as the LIVE
/// layout spells it, and never the retired `packages/` directory the tool
/// stopped reading. An operator who follows a stale recipe creates a directory
/// no resolution looks in, and the message is the only place the recipe
/// appears.
#[test]
fn the_no_source_bails_name_the_live_project_local_registry() {
    let project = tempfile::tempdir().unwrap(); // no packages root, no embedded
    let live = vibe_core::machine_json_path(&vibe_core::layout::current_packages_root());
    for offline in [false, true] {
        let result = build_install_resolver(
            &PackageSourceOptions::default(),
            &empty_manifest(),
            None,
            project.path(),
            &GlobalRegistryConfig::default(),
            offline,
            &[],
        );
        let Err(bail) = result else {
            // The one legal success with zero sources: the offline posture
            // over a warm machine store (PROP-010 §2.6). The store here is
            // the isolated per-process home, so this is a fact about the
            // fixture, never about the operator's machine.
            assert!(
                offline && !vibe_registry::store::list_all().is_empty(),
                "no source at all must bail (offline = {offline})"
            );
            continue;
        };
        let text = bail.to_string();
        assert!(
            text.contains(&format!("`{live}/`")),
            "the bail must name the live project-local registry `{live}/`; got: {text}"
        );
        // The retired spelling. Skipped when the live layout's own answer IS
        // `packages` (the pre-flip layout), where the needle is the truth.
        if live != "packages" {
            assert!(
                !text.contains("`packages/`"),
                "the bail must not name the retired `packages/` directory; got: {text}"
            );
        }
    }
}

// ---- `any_package_source`: the same question, without opening anything -----

/// A machine-global config carrying one `file://` registry rooted at `dir` —
/// the `~/.vibe/registry.toml` shape a developer uses for a registry that is
/// theirs and not the team's (PROP-002 `##GLOBAL-REGISTRY-FILE`).
fn global_with_local_registry(dir: &Path) -> GlobalRegistryConfig {
    toml::from_str(&format!(
        "[[registry]]\nname = \"machine\"\nurl = \"file:///{}\"\n",
        dir.to_string_lossy().replace('\\', "/")
    ))
    .unwrap()
}

/// A manifest whose only dependency is a git source and which declares no
/// `[[registry]]` — the git repository IS the resolver (PROP-002 §2.4.1).
fn manifest_with_a_git_source() -> Manifest {
    Manifest::parse_str(
        "[package]\ngroup = \"org.vibevm\"\nname = \"x\"\nkind = \"flow\"\nversion = \"0.1.0\"\n\n\
         [requires.packages]\n\
         \"org.demo/tools\" = { git = \"https://example.invalid/tools.git\", tag = \"v0.1.0\" }\n",
    )
    .unwrap()
}

/// [`any_package_source`] is the negation of the builder's "nothing can serve"
/// bail, source by source — that is the whole reason a command may refuse on
/// it. Every case is checked BOTH ways: the predicate's answer, and whether
/// the builder really builds a resolver. A case where the two disagree is the
/// defect this pairing exists to catch — `vibe update` refused every project
/// whose registries came from the machine file, fifteen lines before building
/// a resolver that honours it.
#[test]
fn any_package_source_agrees_with_the_builder_source_by_source() {
    let bare = tempfile::tempdir().unwrap();
    let served = tempfile::tempdir().unwrap();
    write_registry_package(served.path(), "org.demo", "tools", "0.1.0", "served");
    let in_tree = temp_project_with_packages("org.demo", "tools", "in tree");
    let embedded = tempfile::tempdir().unwrap();
    write_registry_package(embedded.path(), "org.demo", "tools", "0.1.0", "embedded");

    let check = |label: &str,
                 options: &PackageSourceOptions,
                 manifest: &Manifest,
                 embedded_root: Option<&Path>,
                 project_root: &Path,
                 global: &GlobalRegistryConfig,
                 expected: bool| {
        let predicate = any_package_source(
            options,
            manifest,
            embedded_root,
            project_root,
            global,
            // online: the store rung has its own test below.
            false,
        );
        assert_eq!(predicate, expected, "any_package_source: {label}");
        let built = build_install_resolver(
            options,
            manifest,
            embedded_root,
            project_root,
            global,
            false,
            &[],
        )
        .map(|_| ())
        .is_ok();
        assert_eq!(
            predicate, built,
            "the predicate and the builder must agree: {label}"
        );
    };

    let default = PackageSourceOptions::default();
    let none = GlobalRegistryConfig::default();
    check(
        "nothing anywhere",
        &default,
        &empty_manifest(),
        None,
        bare.path(),
        &none,
        false,
    );
    check(
        "the machine-global registry file alone",
        &default,
        &empty_manifest(),
        None,
        bare.path(),
        &global_with_local_registry(served.path()),
        true,
    );
    check(
        "a project-local packages root alone",
        &default,
        &empty_manifest(),
        None,
        in_tree.path(),
        &none,
        true,
    );
    check(
        "a source build's embedded registry alone",
        &default,
        &empty_manifest(),
        Some(embedded.path()),
        bare.path(),
        &none,
        true,
    );
    check(
        "a declared git source alone",
        &default,
        &manifest_with_a_git_source(),
        None,
        bare.path(),
        &none,
        true,
    );
    check(
        "an explicit --registry alone",
        &PackageSourceOptions {
            registry: Some(served.path().to_path_buf()),
            ..PackageSourceOptions::default()
        },
        &empty_manifest(),
        None,
        bare.path(),
        &none,
        true,
    );
    // The suppression knobs take the sources away again — the predicate reads
    // the same options the builder reads, so it must follow them.
    check(
        "a project-local packages root, with --no-prefer-local",
        &PackageSourceOptions {
            no_prefer_local: true,
            ..PackageSourceOptions::default()
        },
        &empty_manifest(),
        None,
        in_tree.path(),
        &none,
        false,
    );
    check(
        "an embedded registry, with --no-default-registry",
        &PackageSourceOptions {
            no_default_registry: true,
            ..PackageSourceOptions::default()
        },
        &empty_manifest(),
        Some(embedded.path()),
        bare.path(),
        &none,
        false,
    );
}

/// The offline rung of the same agreement: with zero registries the warm
/// machine store is itself a source (PROP-010 §2.6), and a cold one is not.
/// The store here is the isolated per-process home (`vibe_test_support`), so
/// "cold" is a fact about the fixture and not about the operator's machine.
#[test]
fn offline_any_package_source_follows_the_store() {
    let bare = tempfile::tempdir().unwrap();
    let warm = !vibe_registry::store::list_all().is_empty();
    assert_eq!(
        any_package_source(
            &PackageSourceOptions::default(),
            &empty_manifest(),
            None,
            bare.path(),
            &GlobalRegistryConfig::default(),
            true,
        ),
        warm,
        "under --offline the store decides when nothing else can serve"
    );
}
