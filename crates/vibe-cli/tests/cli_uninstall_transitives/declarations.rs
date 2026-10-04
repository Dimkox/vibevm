//! Declaration forms, durable boot-failure boundary and safe empty-container cleanup.
use super::*;

#[test]
fn empty_containers_removed_but_untracked_sibling_preserved() {
    let w = World::new(&["a"], &[("a", &["b"]), ("b", &[])]);
    let parent = w.slot("b").parent().unwrap().to_path_buf();
    fs::write(parent.join("owner.txt"), "keep").unwrap();
    w.remove("org.test/a", w.root());
    assert!(!w.slot("a").parent().unwrap().exists());
    assert!(!w.slot("b").exists());
    assert_eq!(
        fs::read_to_string(parent.join("owner.txt")).unwrap(),
        "keep"
    );
}

#[test]
fn git_declaration_removed_without_fetching() {
    let w = World::new(&["a"], &[("a", &["b"]), ("b", &[])]);
    fs::write(w.root().join("vibe.toml"), "[project]\nname = \"test\"\nversion = \"0.1.0\"\n[requires.packages]\n\"org.test/a\" = { git = \"https://invalid.example/not-contacted.git\", tag = \"v1.0.0\" }\n").unwrap();
    w.remove("org.test/a", w.root());
    assert!(w.names().is_empty());
    let manifest = vibe_core::manifest::Manifest::read(w.root().join("vibe.toml")).unwrap();
    assert!(manifest.requires.git_packages.is_empty());
}

#[test]
fn workspace_placeholder_declaration_and_metadata_removed() {
    let w = World::new(&["a"], &[("a", &["b"]), ("b", &[])]);
    fs::write(
        w.root().join("vibe.toml"),
        r#"[project]
name = "test"
version = "0.1.0"
[workspace]
members = []
[workspace.versions]
chosen = "=1.0.0"
[requires.packages]
"org.test/a" = { version.var = "chosen", link = "static" }
"#,
    )
    .unwrap();
    w.remove("org.test/a", w.root());
    assert!(w.names().is_empty());
    let manifest = vibe_core::manifest::Manifest::read(w.root().join("vibe.toml")).unwrap();
    assert!(manifest.requires.is_empty());
    assert!(manifest.workspace.is_some());
}

#[test]
fn boot_failure_keeps_durable_pruned_world() {
    let w = World::new(&["a"], &[("a", &["b"]), ("b", &[])]);
    let index = w.root().join(common::index_rel());
    fs::remove_file(&index).unwrap();
    fs::create_dir(&index).unwrap();
    fs::write(index.join("owner.txt"), "do not replace").unwrap();
    w.user
        .vibe()
        .args(["uninstall", "org.test/a", "--assume-yes", "--path"])
        .arg(w.root())
        .assert()
        .failure();
    assert!(w.names().is_empty());
    assert!(
        vibe_core::manifest::Manifest::read(w.root().join("vibe.toml"))
            .unwrap()
            .requires
            .is_empty()
    );
    assert!(!w.slot("a").exists());
    assert!(!w.slot("b").exists());
    assert_eq!(
        fs::read_to_string(index.join("owner.txt")).unwrap(),
        "do not replace"
    );
}

#[test]
fn removed_feature_metadata_pruned_without_changing_survivor_features() {
    let w = World::new(
        &["a", "other"],
        &[("a", &["b"]), ("b", &[]), ("other", &[])],
    );
    let path = w.root().join("vibe.lock");
    let mut lock = Lockfile::read(&path).unwrap();
    lock.meta.active_features = vec![
        "org.test/a/first".into(),
        "org.test/b/second".into(),
        "org.test/other/kept".into(),
    ];
    lock.write(&path).unwrap();
    w.remove("org.test/a", w.root());
    assert_eq!(
        Lockfile::read(&path).unwrap().meta.active_features,
        ["org.test/other/kept"]
    );
}
