//! A malformed distribution manifest must fail without publishing an instance.
#![cfg(test)]

use super::*;
use crate::commands::vvm::model::Kind;

#[test]
fn distribution_file_missing_from_manifest_returns_copy_error() {
    let temp = tempfile::tempdir().unwrap();
    let store = VersionStore::new(temp.path().join("opt"));
    let source = temp.path().join("vibe");
    fs::write(&source, b"payload").unwrap();
    let dist = vec![(source, BINARY_NAME.to_string())];
    let id = VersionId::new(Kind::Tag, "1.0.0");

    let error = place(&store, &id, 1, &dist, &Manifest::default(), None).unwrap_err();
    assert!(matches!(&error, PlaceError::Copy { source, .. }
        if source.kind() == io::ErrorKind::InvalidData));
    assert!(error.to_string().contains("does not cover the placed file"));
    assert!(!store.instance_dir(&id, 1).exists());
}
