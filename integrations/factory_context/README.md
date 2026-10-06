# Factory context: data-only preparation profile

This optional integration implements the VibeVM-facing **preparation** part of the factory upgrade. It consumes an already-resolved VibeVM lock and explicitly supplied package directories, captures authorized source bytes, builds deterministic context, publishes immutable generations, verifies offline replay and exports vendor-neutral sources/bindings. It does not run an agent, resolve new versions, install packages or modify factory code. It is disabled unless explicitly enabled.

Specification: `Dimkox/adaptive-grok-build-pro@737867129e703fd63c30e567a195f98353fe9c1e`, `engineering/changes/20260924-factory-unified-upgrade/FACTORY_UNIFIED_UPGRADE_TZ.md`, sections 4.1/4.2 (F19–F24 and applicable F17/F25/F26). Upstream format/code baseline: `30d217bfce47bcaccadabd9468f00e315dbcfead`. This is not completion of the factory's entire 26-requirement specification.

## Architecture and supported profile

The reuse/build decision is to reuse VibeVM's resolved graph and existing hash recipes, not to add another resolver. `boundary.py` is a conservative reader; `context.py` owns the snapshot and explicit mappings; `store.py` owns preparation generations; `boot.py` is a pure managed-block reconciler; `telemetry.py` emits facts for the existing factory ledger. No Rust core, root instruction, release, CI or external workstream changes are needed.

Runtime: Python standard library, syntax floor 3.11, Linux/POSIX `dir_fd`, `O_NOFOLLOW`, `flock` and same-filesystem atomic rename. Executed qualification in this change is limited to Linux/Python 3.13.5. Windows, other Python versions, network filesystems and deployment durability across machine/power loss are not qualified.

Input profile: lock schema 7; `flow` packages only; stable three-component versions; exact frozen transitive versions; exact/caret/tilde authored constraints. Prereleases, arbitrary semver expressions, overrides, app/MCP/lang packages and executable manifest extensions fail closed. This deliberately does not admit the upstream repository's entire redbook/development lock. Only a small project-owned data-only subset is intended.

Tree hashes follow the pinned `crates/vibe-index/src/content_hash.rs` and `formats/hash_recipes/1.toml`: sorted normalized UTF-8 POSIX path, NUL, raw file bytes, NUL. Both `sha256:` and `sha256-tree/1:` require full lowercase 64-digit digests. Recipe-0 compatibility is explicitly POSIX, not a claim about Windows-generated ordering. Excluded names are `.git`, `.vibe`, `target`, `node_modules`, `.vibeignore`. Independent golden vectors are tested; Rust binary parity has not been run.

## Caller contract and trust boundary

The authenticated host supplies the workspace root, tenant/repository identity, request and **separate trusted current policy**. Never accept policy from an agent, package or downloaded snapshot. The JSON policy is not a signature, M3 grant or authentication mechanism. The host must derive it from its existing governance/access layer immediately before use. Origin/reference values are admitted provenance assertions, not network-verified repository ownership. URLs are never fetched.

The request has these required closed-schema fields:

- `schema_version: 1`; `tenant`, `target_repository`, `change_id`, `route_id`.
- `source_snapshot: {commit, tree_digest}`, `change_spec_digest`, `upstream_commit`.
- `lock_path`, `manifest_path`, `packages` (exact package ID to relative directory), `facts`.
- `settings: {dialect: "markdown", overrides: {}}`.
- `sources`: ordered `{id, package, path, mandatory, scope, reason, when}`. `package` is an exact ID or null for local project data. `when` is null or `{fact, equals}` with bounded scalar values.
- `bindings`: `{criterion, source, repository, rule, revision, digest, relation, mandatory}`.

Current policy fields are `schema_version`, `tenant`, `target_repository`, `packages`, `rules`, `required_sources`, `required_bindings`, `audit_allowed`, `qualified_generations`. Each package grant contains `{content_hash, origin, repository, ref, status, license}`. Each canonical `repository#rule` contains `{revision, digest, status}`. Status is active, revoked or draft. Only an explicitly authorized historical audit can read revoked data; it cannot publish or roll back to it.

`required_sources` is an ordered minimum of `{id, package, path, digest}`; `required_bindings` contains the binding fields above except `mandatory`. Requests cannot remove or demote that minimum. Its source order must be the beginning of the mandatory prefix. Included sources are always captured in full. Unknown conditions on mandatory sources include them within budget; a false condition cannot remove a policy-required source. The host remains responsible for proving supplied impact facts and selecting all applicable domain rules; this integration is not an impact analyzer.

The actual retained local bytes participate in the semantic identity, including dirty specifications. The full candidate Git commit/tree identity and change-spec digest are caller-supplied: this integration does **not** prove that an arbitrary whole working tree matches them. Binding validation confirms explicit canonical source/revision/digest relations, not the correctness of a test. `verifies` remains `mapped`, never `passed` or executed evidence.

## API and CLI

From the repository root:

```bash
python -m unittest discover -s integrations/factory_context/tests -v
python -m integrations.factory_context --help
```

The executable synthetic fixture and complete request/policy construction are in `tests/test_adapter.py::fixture`. They contain no production policy, credentials or claims to be the shared F24 benchmark.

For caller-prepared input files, build and publish with:

```bash
python -m integrations.factory_context build \
  --workspace /work/project \
  --request /work/request.json \
  --policy /run/approved-policy.json \
  --store /work/private-context-store \
  --enable
```

The store's parent must exist. The JSON result includes `generation`, `context_digest` and a `current` token `{generation, sequence}`. Persist that **token only** in a JSON file and pass it as `--expect` for a later publication. Omission means the store must still be empty. A conflicting writer is refused, not silently retried. Repeating the same generation with the current expected token is idempotent. Tokens are preparation-store concurrency controls, not factory execution fences.

Replay/export require the exact previously returned generation and explicit authenticated scope:

```bash
python -m integrations.factory_context replay \
  --generation "$GENERATION" --tenant tenant-a --repository example/project \
  --policy /run/approved-policy.json --store /work/private-context-store --enable
python -m integrations.factory_context export \
  --generation "$GENERATION" --tenant tenant-a --repository example/project \
  --policy /run/approved-policy.json --store /work/private-context-store --enable
```

`rollback` additionally requires `--expect`; the exact target must be in the host's current `qualified_generations` and remain admitted. `--audit` is only for replay/export and requires `audit_allowed`. Exit 0 means this local operation succeeded, not that an agent or production profile is qualified. Refusals use exit 2 and a structured code; source contents and URLs are not echoed in errors. Argument-parser failures use argparse's usual exit 2.

Library entry points are `build`, `replay`, `native_export`, `Store.publish/current/load/rollback`, `reconcile_boot`, `usage_event` and `summarize_usage`. `build(..., enabled=True)` is required. All store publications revalidate retained data against the current policy. Execution must keep its explicit generation; it must not reread `current.json` midway through a run.

## Retained artifacts and safety

A generation contains `bundle.json`, `context-manifest.json`, the original `vibe.lock` and authored manifest, `STATIC.md`, `INDEX.json`, selected source files and `bindings.json`. The bundle retains the complete admitted package files and required local bytes as content-addressed objects. Its semantic digest includes the actual adapter source digest, parser runtime, configuration, mandatory policy, canonical mappings and outputs. Raw lock timestamps are transport-only. A different exact adapter/parser build blocks replay; keep the old code/runtime alongside evidence under the host's retention policy.

Replay reads only supplied retained bytes, not ambient caches or URLs. Missing/corrupt data blocks. Generation publication uses staging, fsync, rename and a locked compare-and-swap pointer; failure before the commit point leaves the prior generation active. After a lost acknowledgement, reconcile `current.json` before another attempt. Orphaned staging directories and old generations are retained; no automatic deletion or quota garbage collection is implemented. Retention and storage quotas remain host responsibilities.

No hooks, shell, subprocess, archive extractor, MCP launch, PATH update or self-update are used by the runtime modules. File reads reject traversal, secret paths, unsafe extensions, symlinks, hardlinks, devices, invalid encoding, DTD/entities and XInclude. Bounds apply during enumeration/reads and to aggregate input, objects and logical output, including repeated-source amplification. Defaults: 1 MiB/file, 16 MiB combined input, 1,024 files, depth 16, 128 packages and 1,024 edges. Output and serialized-object multipliers are bounded separately. Formats outside the conservative profile are rejected, not repaired or executed.

Stores require mode 0700 and matching owner/scope. This is **not** isolation against a hostile process with the same Unix UID or host root. Different tenants must have separate host-enforced UIDs/mounts or equivalent access control; deny network and exclude credentials in the actual runner. This change does not supply that runner sandbox. A metadata tenant label cannot replace it. Integrity is rechecked on every load; no shared mutable package cache is used.

`reconcile_boot` preserves unmanaged bytes and refuses duplicate/broken/manual-edited markers without a prior matching block digest. It returns bytes only: it does not write AGENTS.md or bypass the factory's installer. A future installer must coordinate the file's compare-and-swap and reconcile the actual bootstrap order. Neither generating INDEX nor running this Python CLI proves that Claude/Codex/Qwen read anything.

Telemetry includes failed attempts, monotonic durations with an explicit clock domain, and unknown values for unmeasured provider tokens/cost/cache/IO. Bundle size is labeled `snapshot_serialized_bytes`, never total IO. The library rejects interval unions from different clock domains. The CLI emits one operation record; durable collection, global timing, token/provider billing and the existing 12-case F24/F26 runner remain factory-owned.

## Acceptance boundary

| TZ scenarios | Implemented component evidence | Remaining integration qualification |
|---|---|---|
| AC83–84 | Closed frozen graph, constraints/cycles, complete hashes, package and retained-object corruption tests | Real supported VibeVM profile/registry provenance; no resolver executed here |
| AC85–86 | Offline replay after original files disappear, missing-object failures, current origin/status/license checks, audit separation | Trusted M3/admission caller, actual retention/access policy |
| AC87–88 | Pure boot reconciliation, mandatory minimum/order, stable rendering, semantic input identity | Existing installer templates, full candidate binding and verified impact facts |
| AC89 | Descriptor-relative real filesystem tests, special files/XML/bounds, no runtime launch path | Host sandbox, archive acquisition, network/mount isolation |
| AC90 | Explicit mapping states and mandatory binding rejection; no fake executed verdict | Existing M6/M7 tests and negative controls |
| AC91 | Injected pre-pointer crash, threads and real process race, CAS, frozen prior generation, qualified rollback | Host crash/power-loss rehearsal and run-level fencing |
| AC92 | Owner/scope refusal, private permissions, tamper detection, no shared cache | Adversarial cross-UID/mount access test; labels alone are insufficient |
| AC93 | Vendor-neutral source/revision/text/binding export without VibeVM binary | Qualified native factory consumer and explicit new run/snapshot |
| AC94 | Not run; local Python CLI is explicitly not a coding agent | Exact real CLI/dialect capture and independent acceptance |

Shared 12-case F24/F26 comparison, actual token/cost benefit, external Trust CI, independent reviewer and production activation are **not run/not qualified**. No new benchmark or universal evaluator is introduced. The adapter may remain disabled or be rejected without blocking native factory operation. `authority_effect` is always `none`; M8 qualifying contribution is zero.
