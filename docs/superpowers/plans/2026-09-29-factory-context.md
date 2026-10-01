# Factory context data-only adapter implementation plan

> For agentic workers: use superpowers:executing-plans. This work is explicitly requested in the VibeVM fork; factory integration is a later change.

**Goal:** Provide a bounded, offline, opt-in consumer of frozen VibeVM packages that produces reproducible context generations and a vendor-neutral export.

**Architecture:** Reuse the upstream resolved schema-7 lock graph and tree-hash recipes. Do not resolve versions or invoke the VibeVM installer, lifecycle, MCP, agents, network, or shell. The Python standard-library adapter is a separate, replaceable integration seam. Source snapshots and current admission policy come from the authorized caller; outputs never grant execution, merge, or deployment authority.

**Tech stack:** Python 3.11+ standard library; Linux/POSIX descriptor-relative filesystem operations; no new runtime dependencies, CI workflows, database, scheduler or evaluator.

**Spec:** Dimkox/adaptive-grok-build-pro@737867129e703fd63c30e567a195f98353fe9c1e, engineering/changes/20260924-factory-unified-upgrade/FACTORY_UNIFIED_UPGRADE_TZ.md sections 4.1/4.2, AC83–AC94. Upstream baseline: 30d217bfce47bcaccadabd9468f00e315dbcfead.

## Global constraints

Default off. Data only. Preserve project-owned rules. Hashes are integrity, not admission. All unsafe/unknown formats block rather than fall back. No new benchmark corpus. No production activation or factory changes. Existing root instructions, Rust code and release artifacts stay untouched. Current policy must be supplied separately from package/snapshot bytes. Different tenants require separate OS-isolated roots; this library is not authentication or a container runtime.

## Review focus

Symlink and hardlink races; malformed/oversized parsers and paths; graph ambiguity and drift; current revocation despite historical intact bytes; failed/concurrent publication and old-run identity. Tests must cover these at the actual filesystem boundary.

## Task 1 — Frozen data admission

Files: integrations/factory_context/boundary.py and tests/test_adapter.py.
Interfaces: Problem, Limits, read_tree, tree_hash, parse_lock, validate_manifest.
- [x] Write failing tests for bounded no-follow reads, tree recipe golden vectors, schema/graph validation, unknown kinds and exact pins.
- [x] Implement bounded reads, UTF-8/XML checks, lock validation (no resolver), and package identity checks.
- [x] Run focused tests; retain the real red and green results.

## Task 2 — Reproducible snapshot

Files: integrations/factory_context/context.py, __init__.py and tests/test_adapter.py.
Interfaces: build(workspace, request, policy, enabled=False), replay(bundle, policy, tenant, repository, audit=False), native_export.
- [x] Test deterministic rendering, conditional mandatory sources, dirty bytes, current origin/status/license admission, mapping states and offline replay.
- [x] Implement closed request/policy schemas, raw-input retention, full snapshot identities, mandatory-first boot and canonical rule mappings.
- [x] Rebuild from retained objects only and compare the complete generation; no cache or network fallback.

## Task 3 — Atomic lifecycle and boot reconciliation

Files: integrations/factory_context/store.py, boot.py and tests/test_adapter.py.
Interfaces: Store.publish/current/load/rollback, reconcile_boot.
- [x] Test concurrent compare-and-swap, injected crash, frozen old run, corruption, tenant mismatch, protected rollback and malformed managed blocks.
- [x] Implement private immutable generations, descriptor-relative writes, fsync/rename commit point and independent current policy checks.
- [x] Ensure export needs no upstream binary and cannot silently replace a running snapshot.

## Task 4 — CLI, telemetry and qualification boundary

Files: integrations/factory_context/__main__.py, telemetry.py, README.md and tests/test_adapter.py.
- [x] Test a real local CLI build/replay/export sequence and structured errors; do not call this live coding-agent qualification.
- [x] Emit lifecycle facts including failures and unknown provider/token/cost values; no new evaluator.
- [x] Document exact supported profile, commands, trust boundary, source references and unexecuted gates.
- [x] Run all tests, compileall and a runtime side-effect import scan.
- [ ] Verify uploaded Git blob identities and open a draft PR without merging; record publication in the PR receipt.

## Delivery limits

AC94, the shared 12-task F24/F26 comparison, independent review/Trust CI and factory wiring require their real environments and remain not_run. No synthetic test is promoted to those results. The standalone adapter does not implement unrelated F01–F18 or replace M3/M5/M6/M7.

## Execution ledger

Runtime and tests were implemented in isolated local staging; upstream source context was read through the GitHub connector. This is not a complete local git clone and no upstream Rust build is claimed. Initial absent-feature run: 75 failing tests. First implementation: 75 passing tests. Review probes exposed admission-before-read, aggregate/output bounds, malformed-type errors, inaccurate IO labeling, clock-domain mixing and CAS typing/idempotence; regression tests preceded the fixes. Current suite: 103 passing tests, including required-policy omissions and a real local build/replay/export sequence. Pure characterization tests added after implementation are not described as red/green proofs.

Ruling: current authenticated policy owns the mandatory minimum and order; an untrusted request cannot demote it. Required sources/bindings become semantic snapshot inputs. Whole Git candidate identity, policy authenticity, impact analysis and actual coding-agent consumption remain external qualification gates.

Ruling: no optional provider, custom remote adapter, GitHub Actions or paid model invocation was added to overcome unavailable runtime qualification. Tests do not manufacture a Trust CI result. Final review is a self-review with executable regressions, not an independent agent review.
