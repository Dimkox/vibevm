//! Closed public application launcher names and native command coverage.

specmark::scope!("spec://org.vibevm.core/vibevm/common/PROP-059#binary-ownership");

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(crate) enum LauncherKind {
    Bare,
    Shell,
    Batch,
    PowerShell,
    NativeExecutable,
}

impl LauncherKind {
    pub(crate) fn covers_command_on(self, os: &str) -> bool {
        match os {
            "windows" => matches!(
                self,
                Self::Bare | Self::Batch | Self::PowerShell | Self::NativeExecutable
            ),
            "linux" | "macos" => matches!(self, Self::Bare | Self::Shell),
            _ => false,
        }
    }
}

pub(crate) fn launcher_kind(destination: &str, command: &str) -> Option<LauncherKind> {
    if destination == command {
        return Some(LauncherKind::Bare);
    }
    let suffix = destination.strip_prefix(command)?;
    match suffix {
        ".sh" => Some(LauncherKind::Shell),
        ".cmd" | ".bat" => Some(LauncherKind::Batch),
        ".ps1" => Some(LauncherKind::PowerShell),
        ".exe" => Some(LauncherKind::NativeExecutable),
        _ => None,
    }
}

pub(crate) fn launcher_belongs_to_command(name: &str, commands: &[String]) -> bool {
    commands
        .iter()
        .any(|command| launcher_kind(name, command).is_some())
}
