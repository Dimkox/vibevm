//! The one OS-specific operation scrape needs: atomic rename without replace.

specmark::scope!("spec://org.vibevm.core/vibevm/common/PROP-056#SEC-NO-FOLLOW");

use super::tree::EntryState;
use crate::Pinned;

#[derive(Debug)]
pub(super) enum NoReplaceError {
    #[cfg(windows)]
    Occupied,
    #[cfg(windows)]
    SourceChanged,
    #[cfg(windows)]
    SourceReappeared,
    #[cfg(windows)]
    CrossFilesystem,
    Unsupported,
    #[cfg(windows)]
    Io(std::io::Error),
}

pub(super) enum NativeCreateError {
    #[cfg(windows)]
    NotCreated(std::io::Error),
    #[cfg(windows)]
    CreatedButUnsealed(std::io::Error),
    #[cfg(not(windows))]
    Unsupported,
}

pub(super) enum NativeRemoveError {
    #[cfg(windows)]
    Changed(String),
    #[cfg(windows)]
    Io(std::io::Error),
    #[cfg(not(windows))]
    Unsupported,
}

include!("platform/operations.rs");
include!("platform/windows_abi.rs");
include!("platform/fallback.rs");
