//! Regression (2026-09-30, found while converting FPF-Spec Part G): a nested
//! list item whose text begins with a multibyte character panicked the
//! Markdown frontend. `md_in::item_unit` sliced the opener line at
//! `indent + list_marker_len(line)`, but `list_marker_len` already counts
//! the indent, so the slice landed inside `Γ` (`byte index is not a char
//! boundary`). On ASCII text the same double count merely missed the GFM
//! task box of nested items, so they were silently not restored.

use vibe_specdoc::{from_markdown, to_xml};

#[test]
fn nested_item_starting_with_a_multibyte_char_converts() {
    let md = "# probe {#root}\n\n- item\n  * `ΓFoldRef.edition?`\n  - `Φ/Ψ policy-ids?`\n";
    let doc = from_markdown(md).expect("the nested items parse");
    let xml = to_xml(&doc);
    assert!(xml.contains("ΓFoldRef.edition?"), "{xml}");
    assert!(xml.contains("Φ/Ψ policy-ids?"), "{xml}");
}

#[test]
fn nested_task_box_is_restored_at_the_head_of_its_item() {
    let md = "# probe {#root}\n\n- item\n  - [ ] Γ nested task\n";
    let doc = from_markdown(md).expect("the nested task item parses");
    let xml = to_xml(&doc);
    assert!(xml.contains("[ ] Γ nested task"), "{xml}");
    assert!(
        !xml.contains("[ ] [ ]"),
        "the box must not be doubled: {xml}"
    );
}
