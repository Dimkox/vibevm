//! Pure handler envelope projection from the retained effective world.

specmark::scope!("spec://org.vibevm.core/vibevm/common/PROP-054#ENGINE-ALGORITHM");

use super::*;

pub(super) fn envelope_project(provider: &HostProvider, selected: &Path) -> EnvelopeProject {
    let (name, kind) = match &provider.identity {
        HostIdentity::UngroupedProject(name) => (name.clone(), "project".to_string()),
        HostIdentity::Coordinate(identity) => (
            identity.name().to_string(),
            provider
                .kind
                .map_or_else(|| "project".to_string(), |kind| kind.as_str().to_string()),
        ),
        HostIdentity::VirtualWorkspace => {
            ("<virtual-workspace>".to_string(), "workspace".to_string())
        }
    };
    EnvelopeProject {
        kind,
        manifest: vibe_core::machine_json_path(&selected.join(Manifest::FILENAME)),
        name,
        root: vibe_core::machine_json_path(selected),
        spec_roots: vec![vibe_core::machine_json_path(
            &selected.join(vibe_core::layout::current_specs_root()),
        )],
        version: provider.version.clone(),
    }
}

pub(super) fn envelope_world(
    workspace: &Workspace,
    installed: &[DependencyExtensionSource],
) -> EnvelopeWorld {
    EnvelopeWorld {
        deps_root: vibe_core::machine_json_path(&workspace.vibedeps_root()),
        lockfile: vibe_core::machine_json_path(&workspace.lockfile_path()),
        packages: installed
            .iter()
            .map(|source| WorldPackage {
                group: source.provider.id.group().to_string(),
                kind: source.provider.kind.as_str().to_string(),
                name: source.provider.id.name().to_string(),
                slot: vibe_core::machine_json_path(&source.provider.root),
                version: source.provider.version.clone(),
            })
            .collect(),
    }
}
