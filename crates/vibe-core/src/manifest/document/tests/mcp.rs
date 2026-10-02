//! Local and remote MCP manifest delivery and pinning contracts.

use super::*;

/// A minimal, law-abiding `mcp`-kind manifest: one server, its binary,
/// exact-pinned requirement (PROP-027; VIBEVM-SPEC §4.1).
fn mcp_manifest(requires_line: &str, server_tail: &str) -> String {
    format!(
        r#"
[package]
group = "org.vibevm"
name = "rust-ai-native-mcp"
kind = "mcp"
version = "0.6.0"
license = "EULA"
description = "the AI-Native Rust discipline over MCP"
[requires.packages]
{requires_line}
[[binary]]
name = "rust-ai-native-mcp"
crate = "crates/rust-ai-native-mcp"
[[mcp_server]]
name = "rust-ai-native"
binary = "rust-ai-native-mcp"
{server_tail}
"#
    )
}

#[test]
#[verifies("spec://org.vibevm.core/vibevm/modules/vibe-mcp/PROP-027#manifest")]
fn mcp_kind_manifest_parses_under_its_laws() {
    let raw = mcp_manifest(
        "\"stack:org.vibevm/rust-ai-native-lang\" = \"=0.6.0\"",
        "args = [\"--path\", \"{project_root}\"]\n",
    );
    let m = Manifest::parse_str(&raw).unwrap();
    assert_eq!(m.require_package().unwrap().kind, PackageKind::Mcp);
    assert_eq!(m.mcp_servers.len(), 1);
    assert_eq!(
        m.mcp_servers[0].binary.as_deref(),
        Some("rust-ai-native-mcp")
    );
    // Round-trips through serialisation.
    let back = Manifest::parse_str(&toml::to_string_pretty(&m).unwrap()).unwrap();
    assert_eq!(m, back);
}

#[test]
#[verifies("spec://org.vibevm.core/vibevm/modules/vibe-mcp/PROP-027#manifest")]
fn mcp_server_table_is_refused_outside_the_mcp_kind() {
    let raw = r#"
[package]
group = "org.vibevm"
name = "rust-ai-native-lang"
kind = "stack"
version = "0.6.0"
license = "EULA"
description = "x"

[[binary]]
name = "rust-ai-native-mcp"
crate = "crates/rust-ai-native-mcp"

[[mcp_server]]
name = "rust-ai-native"
binary = "rust-ai-native-mcp"
"#;
    let err = Manifest::parse_str(raw).unwrap_err().to_string();
    assert!(err.contains("legal only in `mcp`-kind"), "{err}");
}

#[test]
#[verifies("spec://org.vibevm.core/vibevm/modules/vibe-mcp/PROP-027#manifest")]
fn mcp_kind_without_a_server_is_refused() {
    let raw = r#"
[package]
group = "org.vibevm"
name = "rust-ai-native-mcp"
kind = "mcp"
version = "0.6.0"
license = "EULA"
description = "x"
"#;
    let err = Manifest::parse_str(raw).unwrap_err().to_string();
    assert!(err.contains("at least one [[mcp_server]]"), "{err}");
}

#[test]
#[verifies("spec://org.vibevm.core/vibevm/modules/vibe-mcp/PROP-027#manifest")]
fn mcp_server_binary_must_resolve_and_names_must_be_unique() {
    // Unresolved binary reference.
    let raw = mcp_manifest("\"stack:org.vibevm/rust-ai-native-lang\" = \"=0.6.0\"", "")
        .replace("binary = \"rust-ai-native-mcp\"", "binary = \"ghost\"");
    let err = Manifest::parse_str(&raw).unwrap_err().to_string();
    assert!(err.contains("no [[binary]] declares it"), "{err}");

    // Duplicate server names.
    let raw = mcp_manifest(
        "\"stack:org.vibevm/rust-ai-native-lang\" = \"=0.6.0\"",
        "\n[[mcp_server]]\nname = \"rust-ai-native\"\nbinary = \"rust-ai-native-mcp\"\n",
    );
    let err = Manifest::parse_str(&raw).unwrap_err().to_string();
    assert!(err.contains("duplicate [[mcp_server]] name"), "{err}");
}

#[test]
#[verifies("spec://org.vibevm.core/vibevm/modules/vibe-mcp/PROP-027#manifest")]
fn mcp_server_args_substitute_only_the_closed_set() {
    let raw = mcp_manifest(
        "\"stack:org.vibevm/rust-ai-native-lang\" = \"=0.6.0\"",
        "args = [\"--token\", \"{secret}\"]\n",
    );
    let err = Manifest::parse_str(&raw).unwrap_err().to_string();
    assert!(err.contains("unknown substitution variable"), "{err}");
    assert!(err.contains("{secret}"), "{err}");
}

/// A remote MCP package is declaration-only: it needs no `[[binary]]`.
fn remote_mcp_manifest(server_tail: &str) -> String {
    format!(
        r#"
[package]
group = "ai.lev"
name = "fpf-mcp"
kind = "mcp"
version = "1.0.0"
license = "UPL-1.0"
description = "FPF MCP endpoint"

[[mcp_server]]
name = "fpf"
url = "https://mcp.fpf.tools/mcp"
transport = "streamable-http"
{server_tail}
"#
    )
}

#[test]
#[verifies("spec://org.vibevm.core/vibevm/modules/vibe-mcp/PROP-027#manifest")]
fn remote_mcp_manifest_needs_no_binary_and_round_trips() {
    let m = Manifest::parse_str(&remote_mcp_manifest("")).unwrap();
    assert!(m.binaries.is_empty());
    assert_eq!(m.mcp_servers[0].binary, None);
    assert_eq!(
        m.mcp_servers[0].url.as_deref(),
        Some("https://mcp.fpf.tools/mcp")
    );
    assert_eq!(
        m.mcp_servers[0].transport.as_deref(),
        Some("streamable-http")
    );
    let back = Manifest::parse_str(&toml::to_string_pretty(&m).unwrap()).unwrap();
    assert_eq!(m, back);
}

#[test]
#[verifies("spec://org.vibevm.core/vibevm/modules/vibe-mcp/PROP-027#manifest")]
fn remote_mcp_url_keeps_valid_internationalized_hostname_verbatim() {
    let url = "https://пример.рф/mcp?mode=stream";
    let raw = remote_mcp_manifest("").replace("https://mcp.fpf.tools/mcp", url);
    let m = Manifest::parse_str(&raw).unwrap();
    assert_eq!(m.mcp_servers[0].url.as_deref(), Some(url));
    let back = Manifest::parse_str(&toml::to_string_pretty(&m).unwrap()).unwrap();
    assert_eq!(back.mcp_servers[0].url.as_deref(), Some(url));
}

#[test]
#[verifies("spec://org.vibevm.core/vibevm/modules/vibe-mcp/PROP-027#manifest")]
fn mcp_server_requires_exactly_one_delivery() {
    let both = remote_mcp_manifest("binary = \"fpf-mcp\"");
    let err = Manifest::parse_str(&both).unwrap_err().to_string();
    assert!(err.contains("exactly one of binary or url"), "{err}");

    let neither = remote_mcp_manifest("")
        .replace("url = \"https://mcp.fpf.tools/mcp\"\n", "")
        .replace("transport = \"streamable-http\"\n", "");
    let err = Manifest::parse_str(&neither).unwrap_err().to_string();
    assert!(err.contains("exactly one of binary or url"), "{err}");

    let empty_binary =
        mcp_manifest("", "").replace("binary = \"rust-ai-native-mcp\"", "binary = \"\"");
    let err = Manifest::parse_str(&empty_binary).unwrap_err().to_string();
    assert!(err.contains("empty binary name"), "{err}");
}

#[test]
#[verifies("spec://org.vibevm.core/vibevm/modules/vibe-mcp/PROP-027#manifest")]
fn mcp_server_transport_matches_delivery() {
    let no_transport = remote_mcp_manifest("").replace("transport = \"streamable-http\"\n", "");
    let err = Manifest::parse_str(&no_transport).unwrap_err().to_string();
    assert!(err.contains("requires transport"), "{err}");

    let wrong_transport = remote_mcp_manifest("").replace("streamable-http", "stdio");
    let err = Manifest::parse_str(&wrong_transport)
        .unwrap_err()
        .to_string();
    assert!(err.contains("requires transport"), "{err}");

    let local_http = mcp_manifest("", "transport = \"streamable-http\"");
    let err = Manifest::parse_str(&local_http).unwrap_err().to_string();
    assert!(err.contains("requires stdio"), "{err}");

    let local_stdio = mcp_manifest("", "transport = \"stdio\"");
    Manifest::parse_str(&local_stdio).unwrap();
}

#[test]
#[verifies("spec://org.vibevm.core/vibevm/modules/vibe-mcp/PROP-027#manifest")]
fn remote_mcp_url_and_args_are_checked() {
    for bad in [
        "http://mcp.fpf.tools/mcp",
        "https://",
        "https://user:pass@mcp.fpf.tools/mcp",
        "https://mcp.fpf.tools/mcp#fragment",
        "https://mcp.fpf.tools/a b",
    ] {
        let raw = remote_mcp_manifest("").replace("https://mcp.fpf.tools/mcp", bad);
        let err = Manifest::parse_str(&raw).unwrap_err().to_string();
        assert!(
            err.contains("url must be an HTTPS endpoint"),
            "{bad}: {err}"
        );
    }
    let err = Manifest::parse_str(&remote_mcp_manifest(
        "args = [\"--path\", \"{project_root}\"]",
    ))
    .unwrap_err()
    .to_string();
    assert!(err.contains("cannot declare launch args"), "{err}");
}

#[test]
#[verifies("spec://org.vibevm.core/vibevm/modules/vibe-mcp/PROP-027#exact-pin")]
fn mcp_kind_requires_exact_pins() {
    for bad in ["\"^0.6\"", "\"0.6.0\"", "\"=0.6\"", "\">=0.6.0, <0.7\""] {
        let raw = mcp_manifest(
            &format!("\"stack:org.vibevm/rust-ai-native-lang\" = {bad}"),
            "",
        );
        let err = Manifest::parse_str(&raw).unwrap_err().to_string();
        assert!(
            err.contains("pin every package requirement exactly"),
            "spec {bad} must be refused: {err}"
        );
    }
    // The exact form passes.
    let raw = mcp_manifest("\"stack:org.vibevm/rust-ai-native-lang\" = \"=0.6.0\"", "");
    Manifest::parse_str(&raw).unwrap();
}
