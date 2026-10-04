//! Small installed-world fixtures; never reinstall or contact a registry.
use super::common::{self, UserScratch};
use std::{
    fs,
    path::{Path, PathBuf},
};
use vibe_core::manifest::Lockfile;

pub(super) struct World {
    pub(super) user: UserScratch,
    dir: tempfile::TempDir,
}
impl World {
    pub(super) fn new(roots: &[&str], rows: &[(&str, &[&str])]) -> Self {
        let world = Self {
            user: UserScratch::new(),
            dir: tempfile::tempdir().unwrap(),
        };
        world.user.init_project(world.root());
        world.manifest(world.root(), roots, "");
        let mut lock = format!(
            "[meta]\ngenerated_by = \"test\"\ngenerated_at = \"2026-01-01T00:00:00Z\"\nschema_version = 7\nroot_dependencies = {:?}\n",
            roots
                .iter()
                .map(|name| format!("org.test/{name}@=1.0.0"))
                .collect::<Vec<_>>()
        );
        for (name, children) in rows {
            lock.push_str(&format!("\n[[package]]\nkind = \"flow\"\ngroup = \"org.test\"\nname = \"{name}\"\nversion = \"1.0.0\"\nsource_url = \"local/{name}\"\ncontent_hash = \"sha256:abc\"\ndependencies = {:?}\n", children.iter().map(|child| format!("org.test/{child}@=1.0.0")).collect::<Vec<_>>()));
            fs::create_dir_all(world.slot(name)).unwrap();
            fs::write(world.slot(name).join("vibe.toml"), format!("[package]\ngroup = \"org.test\"\nname = \"{name}\"\nkind = \"flow\"\nversion = \"1.0.0\"\n")).unwrap();
            fs::write(world.slot(name).join("payload"), name).unwrap();
        }
        fs::write(world.root().join("vibe.lock"), lock).unwrap();
        world
    }
    pub(super) fn root(&self) -> &Path {
        self.dir.path()
    }
    pub(super) fn slot(&self, name: &str) -> PathBuf {
        self.root()
            .join(common::deps_root())
            .join(format!("org.test.{name}"))
            .join("1.0.0")
    }
    pub(super) fn manifest(&self, at: &Path, roots: &[&str], extra: &str) {
        fs::create_dir_all(at).unwrap();
        let mut text = format!(
            "[project]\nname = \"test\"\nversion = \"0.1.0\"\n{extra}\n[requires.packages]\n"
        );
        for root in roots {
            text.push_str(&format!("\"org.test/{root}\" = \"=1.0.0\"\n"));
        }
        fs::write(at.join("vibe.toml"), text).unwrap();
    }
    pub(super) fn remove(&self, target: &str, at: &Path) {
        let result = self
            .user
            .vibe()
            .args(["uninstall", target, "--assume-yes", "--json", "--path"])
            .arg(at)
            .assert()
            .success()
            .get_output()
            .stdout
            .clone();
        let report: vibe_wire::generated::uninstall_report::UninstallReport =
            serde_json::from_slice(&result).unwrap();
        assert_eq!(
            usize::try_from(report.removed_count).unwrap(),
            report.paths.len()
        );
        assert!(report.adoption_facts.is_some());
    }
    pub(super) fn names(&self) -> Vec<String> {
        Lockfile::read(self.root().join("vibe.lock"))
            .unwrap()
            .packages
            .into_iter()
            .map(|p| p.name.to_string())
            .collect()
    }
    pub(super) fn snapshot(&self) -> (Vec<u8>, Vec<u8>) {
        (
            fs::read(self.root().join("vibe.lock")).unwrap(),
            fs::read(self.root().join("vibe.toml")).unwrap(),
        )
    }
}
