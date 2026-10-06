//! Select native Git Bash on Windows rather than the WSL `bash.exe` shim.

use anyhow::Result;
use std::path::PathBuf;

#[cfg(not(windows))]
pub(super) fn self_check_bash() -> Result<PathBuf> {
    Ok(PathBuf::from("bash"))
}

#[cfg(windows)]
pub(super) fn self_check_bash() -> Result<PathBuf> {
    use anyhow::{Context, bail};
    let mut command = std::process::Command::new("git");
    command.arg("--exec-path");
    super::scrub_release_credentials(&mut command);
    let output = command
        .output()
        .context("locating native Git Bash; install Git for Windows and put its git.exe on PATH")?;
    if !output.status.success() {
        bail!(
            "git --exec-path failed: {}; install Git for Windows for native self-check",
            String::from_utf8_lossy(&output.stderr).trim()
        );
    }
    let exec_path = String::from_utf8(output.stdout)
        .context("git --exec-path returned non-UTF-8; install Git for Windows")?;
    git_bash_from_exec_path(std::path::Path::new(exec_path.trim()))
}

#[cfg(any(windows, test))]
pub(super) fn git_bash_from_exec_path(exec_path: &std::path::Path) -> Result<PathBuf> {
    use anyhow::{Context, bail};
    let libexec = exec_path
        .parent()
        .context("Git exec path has no parent; install Git for Windows")?;
    let architecture = libexec
        .parent()
        .context("Git exec path has no architecture root")?;
    let root = architecture
        .parent()
        .context("Git exec path has no installation root")?;
    if !exec_path.is_absolute()
        || exec_path.file_name().is_none_or(|name| name != "git-core")
        || libexec.file_name().is_none_or(|name| name != "libexec")
        || architecture
            .file_name()
            .is_none_or(|name| name != "mingw64" && name != "mingw32")
    {
        bail!(
            "Git exec path `{}` is not a Git for Windows installation; put native Git for Windows on PATH to run self-check",
            exec_path.display()
        );
    }
    let bash = root.join("bin/bash.exe");
    let metadata = std::fs::symlink_metadata(&bash).with_context(|| format!(
        "native Git Bash is missing at `{}`; repair Git for Windows (WSL Bash is not supported for native Windows self-check)", bash.display()))?;
    if !metadata.is_file() || metadata.file_type().is_symlink() {
        bail!(
            "native Git Bash `{}` is not a regular executable file; repair Git for Windows",
            bash.display()
        );
    }
    Ok(bash)
}
