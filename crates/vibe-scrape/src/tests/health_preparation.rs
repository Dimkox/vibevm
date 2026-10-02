//! Whole scrape planning with real sealed, owned tool assets and injected discovery.

use std::path::PathBuf;

use crate::health::{
    self, AssetIdentity, AssetRole, HealthError, HealthResolver, ResolveAssetRequest,
    ResolvedCustomLaunch, SystemHealthResolver, TestDiscoveryRequest, TestPresence,
};
use crate::{PreparedScrape, ScrapeMode, ScrapeRequest, init_contract, prepare_with_health};

use super::append_contract;

struct FixtureResolver {
    system: SystemHealthResolver,
    assets: PathBuf,
}

impl HealthResolver for FixtureResolver {
    fn resolve_asset(
        &mut self,
        mut request: ResolveAssetRequest,
    ) -> Result<AssetIdentity, HealthError> {
        if request.role == AssetRole::Cargo {
            request.selector = self
                .assets
                .join(format!("cargo{}", std::env::consts::EXE_SUFFIX))
                .to_str()
                .unwrap()
                .to_owned();
        }
        // The ordinary resolver seals real bytes and resolves companions next
        // to sealed Cargo. No PATH shim or fabricated identity enters this plan.
        self.system.resolve_asset(request)
    }

    fn resolve_custom_launch(
        &mut self,
        check_id: &str,
        interpreter: &str,
        source: &str,
    ) -> Result<ResolvedCustomLaunch, HealthError> {
        assert_eq!(interpreter, "definitely-not-a-vibevm-health-tool");
        let missing = self.assets.join("absent-interpreter");
        assert!(!missing.exists());
        self.system
            .resolve_custom_launch(check_id, missing.to_str().unwrap(), source)
    }

    fn discover_tests(
        &mut self,
        project: &vibe_safefs::Project,
        inventory: &crate::model::Inventory,
        request: &TestDiscoveryRequest,
    ) -> Result<TestPresence, HealthError> {
        self.system.discover_tests(project, inventory, request)
    }
}

fn prepare_fixture(request: ScrapeRequest) -> (PreparedScrape, tempfile::TempDir) {
    // These are honest regular preparation assets, never executed. Their
    // content-derived identities come from the production no-follow resolver.
    let assets = tempfile::tempdir().unwrap();
    for tool in ["cargo", "rustc", "rustdoc"] {
        std::fs::write(
            assets
                .path()
                .join(format!("{tool}{}", std::env::consts::EXE_SUFFIX)),
            format!("owned {tool} preparation fixture; never executed\n"),
        )
        .unwrap();
    }
    let mut preparations = 0;
    let prepared = prepare_with_health(request, |project, contract, inventory| {
        preparations += 1;
        let mut resolver = FixtureResolver {
            system: SystemHealthResolver::new(project),
            assets: assets.path().to_path_buf(),
        };
        health::prepare(project, contract, inventory, &mut resolver)
    })
    .unwrap();
    assert_eq!(
        preparations, 1,
        "one prepared health panel feeds the whole plan"
    );
    // Keep the sealed assets alive through every identity and wire assertion.
    (prepared, assets)
}

#[test]
fn health_is_prepared_once_and_wire_contains_no_placeholder_identity() {
    let source = tempfile::tempdir().unwrap();
    std::fs::create_dir(source.path().join("src")).unwrap();
    std::fs::write(
        source.path().join("Cargo.toml"),
        "[package]\nname='health-fixture'\nversion='0.1.0'\nedition='2024'\n",
    )
    .unwrap();
    std::fs::write(source.path().join("src/lib.rs"), "pub fn fixture() {}\n").unwrap();
    init_contract(source.path()).unwrap();
    let (prepared, _assets) = prepare_fixture(ScrapeRequest {
        root: source.path().to_path_buf(),
        contract: None,
        mode: ScrapeMode::InPlace,
    });
    assert_eq!(
        prepared.health.plan_id,
        prepared.plan.prepared_health.plan_id
    );
    assert_eq!(prepared.health.checks.len(), 1);
    assert!(
        !prepared
            .health
            .blockers
            .iter()
            .any(|blocker| blocker.message.contains("version probe"))
    );
    assert!(
        prepared.health.checks[0]
            .assets
            .iter()
            .all(|asset| asset.version.starts_with("content:sha256:"))
    );
    assert!(
        !prepared
            .plan
            .blockers
            .iter()
            .any(|blocker| blocker.code == "health-preparation-required")
    );
    let json = serde_json::to_string(&prepared.plan.to_wire().unwrap()).unwrap();
    assert!(json.contains("health_plan_id"));
    assert!(!json.contains("health-preparation-required"));
}

#[test]
fn health_resolver_failure_is_a_typed_blocker_without_fake_wire_row() {
    let source = tempfile::tempdir().unwrap();
    std::fs::create_dir(source.path().join("src")).unwrap();
    std::fs::write(
        source.path().join("Cargo.toml"),
        "[package]\nname='health-fixture'\nversion='0.1.0'\nedition='2024'\n",
    )
    .unwrap();
    std::fs::write(source.path().join("src/lib.rs"), "pub fn fixture() {}\n").unwrap();
    init_contract(source.path()).unwrap();
    std::fs::write(source.path().join("health.py"), "pass\n").unwrap();
    append_contract(
        source.path(),
        r#"
[[healthcheck]]
id = "missing-interpreter"
kind = "custom"
root = "."
source = "health.py"
snapshot = ["health.py"]
interpreter = "definitely-not-a-vibevm-health-tool"
argv = []
protocol = "exit-code"
reads = ["**"]
writes = []
spawn = true
network = "inherit"
timeout_seconds = 1
"#,
    );
    let (prepared, _assets) = prepare_fixture(ScrapeRequest {
        root: source.path().to_path_buf(),
        contract: None,
        mode: ScrapeMode::InPlace,
    });
    assert!(prepared.plan.blockers.iter().any(|blocker| {
        blocker.code == "health-preparation-failed"
            && blocker.rule_id.as_deref() == Some("missing-interpreter")
    }));
    let wire = prepared.plan.to_wire().unwrap();
    assert_eq!(
        wire.healthchecks.len(),
        1,
        "only the valid Cargo row survives"
    );
    let json = serde_json::to_string(&wire.healthchecks).unwrap();
    assert!(!json.contains("missing-interpreter"));
}
