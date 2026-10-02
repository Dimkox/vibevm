//! The install-consent port and the CLI dialoguer adapter.

specmark::scope!("spec://org.vibevm.core/vibevm/common/PROP-060#INSTALL-DESTINATION");

use anyhow::{Context, Result, bail};
use dialoguer::Confirm;
use std::path::{Path, PathBuf};
use vibe_orchestrator::ports::ConfirmGate;

use crate::exit_code::InstallError;
use crate::output;

/// CLI confirmation over the invocation's already-resolved posture.
pub(crate) struct CliConfirmGate<'a> {
    ctx: &'a output::Context,
    assume_yes: bool,
    destination: PathBuf,
}

impl<'a> CliConfirmGate<'a> {
    pub(crate) fn new(ctx: &'a output::Context, assume_yes: bool, root: &Path) -> Self {
        Self {
            ctx,
            assume_yes,
            destination: crate::commands::init::strip_unc_public(
                root.join(vibe_core::layout::current_vibedeps_root()),
            ),
        }
    }

    fn project_prompt(&self, packages: usize) -> String {
        format!(
            "Install {packages} package{} into {}?",
            if packages == 1 { "" } else { "s" },
            self.destination.display(),
        )
    }
}

impl ConfirmGate for CliConfirmGate<'_> {
    fn confirm_install(&self, packages: usize) -> Result<()> {
        if self.assume_yes || self.ctx.is_unattended() || self.ctx.is_json() {
            return Ok(());
        }
        if !console::user_attended() {
            bail!(
                "no TTY available for confirmation; re-run with `--assume-yes` to apply this plan non-interactively"
            );
        }
        let approved = self
            .ctx
            .suspend_progress(|| {
                Confirm::new()
                    .with_prompt(self.project_prompt(packages))
                    .default(false)
                    .interact()
            })
            .context("reading user confirmation")?;
        if approved {
            Ok(())
        } else {
            Err(InstallError::UserDeclined.into())
        }
    }
}
