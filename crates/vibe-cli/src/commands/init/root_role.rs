//! Pure planning of the root identity, before any scaffold or settings write.

specmark::scope!("spec://org.vibevm.core/vibevm/common/PROP-024#INIT-ROOT-ROLE");

use std::path::Path;

use anyhow::{Context, Result, bail};
use dialoguer::Select;
use vibe_core::user_config::UserConfig;
use vibe_core::{
    PackageKind,
    manifest::{Manifest, ProjectSection},
};

use super::{
    prompts::{self, ProjectFields},
    validate_group,
};
use crate::{
    cli::{InitArgs, InitType},
    output,
};

pub(super) struct RootPlan {
    pub role: InitType,
    pub fields: ProjectFields,
    pub manifest: Manifest,
}

pub(super) fn plan(
    ctx: &output::Context,
    args: &InitArgs,
    root: &Path,
    user_config: &UserConfig,
    interactive: bool,
) -> Result<RootPlan> {
    if args.translates.is_some() {
        bail!("`--translates` requires the nested `vibe init package <group>/<name>` form");
    }
    let manifest_path = root.join(Manifest::FILENAME);
    if manifest_path.exists() {
        return existing(args, Manifest::read(&manifest_path)?);
    }
    let role = match args.init_type {
        Some(role) => role,
        None if interactive => ctx.suspend_progress(|| {
            let selected = Select::new()
                .with_prompt("Root declaration")
                .items(["project", "package"])
                .default(0)
                .interact()?;
            Ok::<_, anyhow::Error>(if selected == 0 {
                InitType::Project
            } else {
                InitType::Package
            })
        })?,
        None => InitType::Project,
    };
    let default_name = super::helpers::resolve_name(args, root)?;
    let mut fields = prompts::project_fields_from_args(args, &default_name, user_config);
    if role == InitType::Package && args.version.is_none() {
        fields.version = "0.1.0".to_string();
    }
    let (fields, group, kind) = if interactive {
        ctx.suspend_progress(|| {
            let fields = prompts::prompt_fields(args, fields, role == InitType::Package)?;
            let group = match &args.group {
                Some(group) => Some(group.clone()),
                None => {
                    let group =
                        prompts::text("Group (reverse-DNS)", "", role == InitType::Project)?;
                    (!group.trim().is_empty()).then(|| group.trim().to_string())
                }
            };
            let kind = if role == InitType::Package {
                prompts::prompt_kind(args)?
            } else {
                super::package::requested_kind(args)?
            };
            Ok::<_, anyhow::Error>((fields, group, kind))
        })?
    } else {
        (
            fields,
            args.group.clone(),
            super::package::requested_kind(args)?,
        )
    };
    validate_fields(&fields, role == InitType::Package)?;
    if let Some(group) = &group {
        validate_group(group)?;
    }
    let manifest = new_manifest(args, role, group.as_deref(), kind, &fields)?;
    Ok(RootPlan {
        role,
        fields,
        manifest,
    })
}

pub(super) fn validate_fields(fields: &ProjectFields, package: bool) -> Result<()> {
    if package {
        vibe_core::PackageName::parse(&fields.name).context("invalid initialization name")?;
    } else if fields.name.trim().is_empty() {
        bail!("project name must not be empty");
    }
    semver::Version::parse(&fields.version).context("invalid initialization version")?;
    if !matches!(fields.format.as_str(), "normal" | "simple") {
        bail!(
            "invalid initialization format `{}`; expected normal or simple",
            fields.format
        );
    }
    Ok(())
}

fn new_manifest(
    args: &InitArgs,
    role: InitType,
    group: Option<&str>,
    kind: PackageKind,
    fields: &ProjectFields,
) -> Result<Manifest> {
    let mut manifest = Manifest {
        active: args
            .stack
            .as_ref()
            .map(|stack| vibe_core::manifest::ActiveSection {
                stack: Some(stack.clone()),
            }),
        registries: super::resolve_registry_sections(args),
        ..Default::default()
    };
    match role {
        InitType::Project => {
            manifest.project = Some(ProjectSection {
                name: fields.name.clone(),
                group: group.map(vibe_core::Group::parse).transpose()?,
                version: fields.version.clone(),
                spec_format: None,
                authors: fields.authors.clone(),
            })
        }
        InitType::Package => {
            let group = group.context("a package root requires `--group <reverse-DNS>`")?;
            if kind == PackageKind::Doc {
                let doc = super::doc::root_manifest(group, &fields.name, fields)?;
                manifest.package = doc.package;
                manifest.documents = doc.documents;
                manifest.i18n = doc.i18n;
            } else {
                let mut table = toml::Table::new();
                for (key, value) in [
                    ("name", fields.name.as_str()),
                    ("group", group),
                    ("kind", kind.as_str()),
                    ("version", fields.version.as_str()),
                    ("license", fields.license.as_str()),
                    ("description", fields.description.as_str()),
                    ("format", fields.format.as_str()),
                ] {
                    table.insert(key.to_string(), toml::Value::String(value.to_string()));
                }
                table.insert("epoch".into(), toml::Value::Integer(1));
                table.insert(
                    "authors".into(),
                    toml::Value::Array(
                        fields
                            .authors
                            .iter()
                            .cloned()
                            .map(toml::Value::String)
                            .collect(),
                    ),
                );
                manifest.package = Some(toml::Value::Table(table).try_into()?);
            }
        }
    }
    manifest.validate()?;
    Ok(manifest)
}

fn existing(args: &InitArgs, manifest: Manifest) -> Result<RootPlan> {
    let (role, name, group, version, authors, license, description, format) = if let Some(package) =
        &manifest.package
    {
        (
            InitType::Package,
            package.name.clone(),
            Some(package.group.as_str()),
            package.version.to_string(),
            package.authors.clone(),
            package.license.clone().unwrap_or_default(),
            package.description.clone().unwrap_or_default(),
            match package.format {
                vibe_core::manifest::PackageFormat::Normal => "normal",
                vibe_core::manifest::PackageFormat::Simple => "simple",
            }
            .to_string(),
        )
    } else if let Some(project) = &manifest.project {
        (
            InitType::Project,
            project.name.clone(),
            project.group.as_ref().map(vibe_core::Group::as_str),
            project.version.clone(),
            project.authors.clone(),
            String::new(),
            String::new(),
            "normal".to_string(),
        )
    } else {
        bail!(
            "existing root has no project or package identity; init does not convert workspace roles"
        );
    };
    if args.init_type.is_some_and(|requested| requested != role) {
        bail!("existing root declaration is {role:?}; init does not convert project/package roles");
    }
    let requested_group = args
        .group
        .as_deref()
        .map(|group| {
            validate_group(group)?;
            Ok::<_, anyhow::Error>(vibe_core::Group::parse(group)?)
        })
        .transpose()?;
    if requested_group
        .as_ref()
        .is_some_and(|requested| Some(requested.as_str()) != group)
        || args
            .name
            .as_deref()
            .is_some_and(|requested| requested != name)
    {
        bail!(
            "requested group/name differs from the existing root identity; init preserves authored manifests"
        );
    }
    let requested = prompts::project_fields_from_args(args, &name, &UserConfig::default());
    validate_fields(&requested, role == InitType::Package)?;
    super::package::requested_kind(args)?;
    Ok(RootPlan {
        role,
        fields: ProjectFields {
            name,
            version,
            authors,
            license,
            description,
            format,
        },
        manifest,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use clap::Parser;

    fn args() -> InitArgs {
        match crate::cli::Cli::try_parse_from(["vibe", "init"])
            .unwrap()
            .command
        {
            crate::cli::Command::Init(args) => args,
            _ => panic!("init parser returned another command"),
        }
    }

    fn fields() -> ProjectFields {
        ProjectFields {
            name: "sample".into(),
            version: "1.2.3".into(),
            authors: vec!["A \"Writer\"".into()],
            license: "Proprietary".into(),
            description: "Text with \"quotes\"\nand a newline".into(),
            format: "normal".into(),
        }
    }

    #[test]
    fn declaration_only_package_kinds_roundtrip_as_root_consumers() {
        for kind in [
            PackageKind::Tool,
            PackageKind::Flow,
            PackageKind::Feat,
            PackageKind::Stack,
            PackageKind::Lang,
            PackageKind::Doc,
            PackageKind::App,
        ] {
            let manifest = new_manifest(
                &args(),
                InitType::Package,
                Some("org.example"),
                kind,
                &fields(),
            )
            .unwrap();
            let roundtrip =
                Manifest::parse_str(&toml::to_string_pretty(&manifest).unwrap()).unwrap();
            roundtrip.validate().unwrap();
            assert!(roundtrip.project.is_none());
            let package = roundtrip.package.unwrap();
            assert_eq!(package.kind, kind);
            assert_eq!(package.epoch, Some(1));
            assert_eq!(
                package.description.as_deref(),
                Some(fields().description.as_str())
            );
            assert!(roundtrip.boot_snippet.is_none());
        }
    }

    #[test]
    fn mcp_root_requires_server_declarations_before_scaffolding() {
        let error = new_manifest(
            &args(),
            InitType::Package,
            Some("org.example"),
            PackageKind::Mcp,
            &fields(),
        )
        .expect_err("an MCP package without server declarations must fail core validation");
        assert!(error.to_string().contains("mcp_server"));
    }

    #[test]
    fn project_group_and_version_are_preserved_by_typed_factory() {
        let manifest = new_manifest(
            &args(),
            InitType::Project,
            Some("org.example"),
            PackageKind::Tool,
            &fields(),
        )
        .unwrap();
        let roundtrip = Manifest::parse_str(&toml::to_string_pretty(&manifest).unwrap()).unwrap();
        assert!(roundtrip.package.is_none());
        let project = roundtrip.project.unwrap();
        assert_eq!(project.group.unwrap().as_str(), "org.example");
        assert_eq!(project.version, "1.2.3");
    }
}
