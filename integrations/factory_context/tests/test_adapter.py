"""Executable checks for the data-only profile; not the F24 benchmark corpus."""
import copy
import hashlib
import importlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

try:
    fc = importlib.import_module('integrations.factory_context')
    if not hasattr(fc, 'build'):
        fc = None
except ImportError:
    fc = None

PID = 'flow:org.example/rules@1.0.0'
REPO = 'example/project'
COMMIT = 'a' * 40
UPSTREAM = '30d217bfce47bcaccadabd9468f00e315dbcfead'


def sha(raw):
    return 'sha256:' + hashlib.sha256(raw).hexdigest()


def golden_tree(files, label='sha256-tree/1:'):
    raw = b''.join(k.encode() + b'\0' + files[k] + b'\0' for k in sorted(files))
    return label + hashlib.sha256(raw).hexdigest()


def fixture(root):
    package = root / 'packages/rules'
    package.mkdir(parents=True)
    raw = b'# Rule A\nNever alter an approved dimension.\n'
    manifest = (b'[package]\nname="rules"\ngroup="org.example"\nkind="flow"\n'
                b'version="1.0.0"\nlicense="UPL-1.0"\n')
    files = {'vibe.toml': manifest, 'rule.md': raw}
    for name, data in files.items():
        (package / name).write_bytes(data)
    content_hash = golden_tree(files)
    lock = ('[meta]\nschema_version=7\ngenerated_by="vibe 1.0.0"\n'
            'root_dependencies=["flow:org.example/rules@^1.0.0"]\n'
            '[[package]]\nkind="flow"\nname="rules"\ngroup="org.example"\n'
            'version="1.0.0"\nsource_url="https://example.org/rules"\n'
            f'content_hash="{content_hash}"\nsource_kind="registry"\n'
            'dependencies=[]\nfiles_written=[]\nadmitted_by="root-edge"\n')
    (root / 'vibe.lock').write_text(lock)
    (root / 'vibe.toml').write_text('[requires.packages]\n"flow:org.example/rules"="^1.0.0"\n')
    (root / 'project.md').write_text('# Project\nLocal instructions.\n')
    request = dict(schema_version=1, tenant='tenant-a', target_repository=REPO,
                   change_id='change-1', route_id='route-1',
                   source_snapshot={'commit': COMMIT, 'tree_digest': sha(b'candidate')},
                   change_spec_digest=sha(b'approved spec'), upstream_commit=UPSTREAM,
                   lock_path='vibe.lock', manifest_path='vibe.toml',
                   packages={PID: 'packages/rules'}, facts={'bitrix': True},
                   settings={'dialect': 'markdown', 'overrides': {}},
                   sources=[dict(id='rule-a', package=PID, path='rule.md', mandatory=True,
                                 scope='all', reason='approved required rule', when=None),
                            dict(id='local', package=None, path='project.md', mandatory=False,
                                 scope='bitrix', reason='confirmed impact',
                                 when={'fact': 'bitrix', 'equals': True})],
                   bindings=[dict(criterion='AC-domain', source='rule-a', repository=REPO,
                                  rule='RULE-A', revision='1', digest=sha(raw),
                                  relation='verifies', mandatory=True)])
    policy = dict(schema_version=1, tenant='tenant-a', target_repository=REPO,
                  packages={PID: dict(content_hash=content_hash, origin='https://example.org/rules',
                                      repository=REPO, ref=COMMIT, status='active', license='UPL-1.0')},
                  rules={REPO + '#RULE-A': dict(revision='1', digest=sha(raw), status='active')},
                  audit_allowed=False, qualified_generations=[])
    policy['required_sources'] = [dict(id='rule-a', package=PID, path='rule.md', digest=sha(raw))]
    policy['required_bindings'] = [{key: value for key, value in request['bindings'][0].items() if key != 'mandatory'}]
    return request, policy


class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(fc, 'factory-context adapter has not been implemented')
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.request, self.policy = fixture(self.root)

    def build(self, **kw):
        return fc.build(self.root, self.request, self.policy, enabled=True, **kw)

    def problem(self, code, fn, *args, **kwargs):
        with self.assertRaises(fc.Problem) as caught:
            fn(*args, **kwargs)
        self.assertEqual(caught.exception.code, code)
        return caught.exception

    def test_default_off(self):
        self.problem('disabled', fc.build, self.root, self.request, self.policy)

    def test_deterministic_and_replay(self):
        first = self.build()
        second = self.build()
        self.assertEqual(first.to_bytes(), second.to_bytes())
        replayed = fc.replay(first, self.policy, 'tenant-a', REPO)
        self.assertEqual(first.to_bytes(), replayed.to_bytes())

    def test_hash_recipe_golden(self):
        files = {'z.txt': b'Z', 'a/b.txt': b'B', 'a.txt': b'A'}
        self.assertEqual(fc.tree_hash(files), golden_tree(files))
        self.assertEqual(fc.tree_hash(files, 'sha256:'), golden_tree(files, 'sha256:'))
        self.assertEqual(fc.tree_hash({}), 'sha256-tree/1:' + hashlib.sha256(b'').hexdigest())

    def test_bound_input(self):
        self.problem('bounds', self.build, limits=fc.Limits(max_file_bytes=10))

    def test_unknown_request_field(self):
        self.request['shell'] = 'do not execute'
        self.problem('schema', self.build)

    def test_unknown_policy_field(self):
        self.policy['allow_everything'] = True
        self.problem('schema', self.build)

    def test_duplicate_json_keys(self):
        self.problem('schema', fc.decode_json, b'{"a":1,"a":2}')

    def test_nonfinite_json(self):
        self.problem('schema', fc.decode_json, b'{"a":NaN}')

    def test_tenant_policy_mismatch(self):
        self.policy['tenant'] = 'tenant-b'
        self.problem('admission', self.build)

    def test_repository_policy_mismatch(self):
        self.policy['target_repository'] = 'other/project'
        self.problem('admission', self.build)

    def test_origin_does_not_follow_identical_hash(self):
        self.policy['packages'][PID]['origin'] = 'https://other.example/rules'
        self.problem('origin', self.build)

    def test_revoked_package(self):
        self.policy['packages'][PID]['status'] = 'revoked'
        self.problem('revoked', self.build)

    def test_unknown_license(self):
        self.policy['packages'][PID]['license'] = ''
        self.problem('license', self.build)

    def test_revocation_checked_on_replay(self):
        bundle = self.build()
        self.policy['packages'][PID]['status'] = 'revoked'
        self.problem('revoked', fc.replay, bundle, self.policy, 'tenant-a', REPO)
        self.policy['audit_allowed'] = True
        self.assertEqual(bundle.id, fc.replay(bundle, self.policy, 'tenant-a', REPO, audit=True).id)
        self.problem('revoked', fc.replay, bundle, self.policy, 'tenant-a', REPO)

    def test_rule_revocation(self):
        self.policy['rules'][REPO + '#RULE-A']['status'] = 'revoked'
        self.problem('mapping', self.build)

    def test_tampered_package(self):
        (self.root / 'packages/rules/rule.md').write_text('different bytes')
        self.problem('integrity', self.build)

    def test_truncated_hash(self):
        path = self.root / 'vibe.lock'
        path.write_text(path.read_text().replace(self.policy['packages'][PID]['content_hash'], 'sha256:abc'))
        self.problem('digest', self.build)

    def test_missing_package(self):
        self.request['packages'][PID] = 'missing'
        self.problem('missing-package', self.build)

    def test_missing_saved_object(self):
        bundle = self.build()
        value = json.loads(bundle.to_bytes())
        del value['objects'][next(iter(value['objects']))]
        self.problem('missing-object', fc.replay, fc.Bundle(value), self.policy, 'tenant-a', REPO)

    def test_corrupt_saved_object(self):
        bundle = self.build()
        value = json.loads(bundle.to_bytes())
        value['objects'][next(iter(value['objects']))] = 'aW52YWxpZA=='
        self.problem('integrity', fc.replay, fc.Bundle(value), self.policy, 'tenant-a', REPO)

    def test_offline_replay_after_original_tree_removed(self):
        bundle = self.build()
        import shutil
        shutil.rmtree(self.root / 'packages')
        (self.root / 'project.md').unlink()
        with patch('socket.socket', side_effect=AssertionError('network forbidden')):
            self.assertEqual(bundle.id, fc.replay(bundle, self.policy, 'tenant-a', REPO).id)

    def test_local_dirty_source_changes_identity(self):
        first = self.build()
        (self.root / 'project.md').write_text('local dirty bytes')
        second = self.build()
        self.assertNotEqual(first.context_digest, second.context_digest)

    def test_observation_clock_does_not_change_context(self):
        first = self.build()
        with patch('time.time', return_value=123456789):
            second = self.build()
        self.assertEqual(first.context_digest, second.context_digest)
        self.assertEqual(first.outputs['STATIC.md'], second.outputs['STATIC.md'])

    def test_lock_timestamp_is_transport_only(self):
        first = self.build()
        path = self.root / 'vibe.lock'
        path.write_text(path.read_text().replace('[meta]', '[meta]\ngenerated_at="2026-09-29T00:00:00Z"'))
        second = self.build()
        self.assertEqual(first.context_digest, second.context_digest)
        self.assertNotEqual(first.id, second.id)

    def test_condition_and_settings_identity(self):
        first = self.build()
        self.request['facts']['bitrix'] = False
        second = self.build()
        self.assertNotEqual(first.context_digest, second.context_digest)
        self.assertNotIn('sources/local.md', second.outputs)

    def test_unknown_mandatory_condition_includes(self):
        self.request['sources'][0]['when'] = {'fact': 'unknown', 'equals': True}
        bundle = self.build()
        self.assertIn(b'Never alter', bundle.outputs['STATIC.md'])
        decision = bundle.value['manifest']['semantic']['decisions'][0]
        self.assertEqual(decision['condition'], 'unknown')
        self.assertTrue(decision['included'])

    def test_false_mandatory_condition_excludes_when_confirmed(self):
        self.request['sources'][0]['when'] = {'fact': 'bitrix', 'equals': False}
        self.problem('mapping', self.build)

    def test_verifies_is_only_mapped(self):
        bundle = self.build()
        bindings = json.loads(bundle.outputs['bindings.json'])
        self.assertEqual(bindings[0]['status'], 'mapped')
        self.assertNotIn('passed', json.dumps(bindings))

    def test_stale_mapping(self):
        self.policy['rules'][REPO + '#RULE-A']['revision'] = '2'
        self.problem('mapping', self.build)

    def test_unknown_relation(self):
        self.request['bindings'][0]['relation'] = 'proves'
        self.problem('mapping', self.build)

    def test_missing_mapping_target(self):
        self.request['bindings'][0]['source'] = 'missing'
        self.problem('mapping', self.build)

    def test_duplicate_canonical_rule(self):
        self.request['bindings'].append(copy.deepcopy(self.request['bindings'][0]))
        self.problem('mapping', self.build)

    def test_source_path_traversal(self):
        self.request['sources'][0]['path'] = '../outside.md'
        self.problem('path', self.build)

    def test_absolute_path(self):
        self.request['manifest_path'] = '/etc/passwd'
        self.problem('path', self.build)

    def test_backslash_path(self):
        self.request['manifest_path'] = '..\\outside'
        self.problem('path', self.build)

    def test_secret_path_not_read(self):
        self.request['sources'][1]['path'] = '.env'
        (self.root / '.env').write_text('CANARY=not-a-secret')
        self.problem('path', self.build)

    def test_package_symlink(self):
        outside = self.root / 'outside.md'
        outside.write_text('canary')
        (self.root / 'packages/rules/escape.md').symlink_to(outside)
        self.problem('path', self.build)

    def test_parent_symlink(self):
        (self.root / 'alias').symlink_to(self.root / 'packages', target_is_directory=True)
        self.request['packages'][PID] = 'alias/rules'
        self.problem('path', self.build)

    def test_hardlink(self):
        os.link(self.root / 'project.md', self.root / 'packages/rules/hard.md')
        self.problem('path', self.build)

    def test_fifo(self):
        os.mkfifo(self.root / 'packages/rules/pipe.md')
        self.problem('path', self.build)

    def test_no_hooks(self):
        path = self.root / 'packages/rules/vibe.toml'
        path.write_bytes(path.read_bytes() + b'\n[lifecycle]\ninstall="touch CANARY"\n')
        files = {p.name: p.read_bytes() for p in path.parent.iterdir()}
        old = self.policy['packages'][PID]['content_hash']
        new = golden_tree(files)
        lock = self.root / 'vibe.lock'
        lock.write_text(lock.read_text().replace(old, new))
        self.policy['packages'][PID]['content_hash'] = new
        self.problem('executable-content', self.build)
        self.assertFalse((self.root / 'CANARY').exists())

    def test_executable_file(self):
        (self.root / 'packages/rules/hook.sh').write_text('touch CANARY')
        self.problem('executable-content', self.build)

    def test_xml_external_entity(self):
        (self.root / 'packages/rules/spec.xml').write_text('<!DOCTYPE r [<!ENTITY x SYSTEM "file:///etc/passwd">]><r>&x;</r>')
        self.problem('xml', self.build)

    def test_invalid_utf8(self):
        (self.root / 'packages/rules/invalid.md').write_bytes(b'\xff')
        self.problem('encoding', self.build)

    def test_depth_limit(self):
        path = self.root / 'packages/rules/a/b/c/d/e.txt'
        path.parent.mkdir(parents=True)
        path.write_text('x')
        self.problem('bounds', self.build, limits=fc.Limits(max_depth=3))

    def test_count_limit(self):
        self.problem('bounds', self.build, limits=fc.Limits(max_files=1))

    def test_aggregate_size_limit(self):
        self.problem('bounds', self.build, limits=fc.Limits(max_total_bytes=100))

    def test_case_collision(self):
        (self.root / 'packages/rules/Rule.md').write_text('other')
        self.problem('path', self.build)

    def test_lock_duplicate_package(self):
        path = self.root / 'vibe.lock'
        raw = path.read_text()
        path.write_text(raw + '\n[[package]]' + raw.split('[[package]]')[1])
        self.problem('graph-conflict', self.build)

    def test_lock_missing_dependency(self):
        path = self.root / 'vibe.lock'
        path.write_text(path.read_text().replace('dependencies=[]', 'dependencies=["flow:org.example/absent@=1.0.0"]'))
        err = self.problem('graph-conflict', self.build)
        self.assertIn('absent', str(err))

    def test_lock_cycle(self):
        path = self.root / 'vibe.lock'
        path.write_text(path.read_text().replace('dependencies=[]', 'dependencies=["flow:org.example/rules@=1.0.0"]'))
        self.problem('graph-cycle', self.build)

    def test_lock_floating_transitive(self):
        path = self.root / 'vibe.lock'
        path.write_text(path.read_text().replace('dependencies=[]', 'dependencies=["flow:org.example/rules@^1.0.0"]'))
        self.problem('graph-conflict', self.build)

    def test_root_version_conflict(self):
        path = self.root / 'vibe.lock'
        path.write_text(path.read_text().replace('@^1.0.0', '@^2.0.0'))
        self.problem('graph-conflict', self.build)

    def test_unknown_lock_schema(self):
        path = self.root / 'vibe.lock'
        path.write_text(path.read_text().replace('schema_version=7', 'schema_version=8'))
        self.problem('schema', self.build)

    def test_override_not_silently_accepted(self):
        self.request['settings']['overrides'] = {PID: '2.0.0'}
        self.problem('graph-conflict', self.build)

    def test_non_data_kind(self):
        path = self.root / 'vibe.lock'
        path.write_text(path.read_text().replace('kind="flow"', 'kind="mcp"'))
        self.problem('executable-content', self.build)

    def test_authored_manifest_graph_mismatch(self):
        (self.root / 'vibe.toml').write_text('[requires.packages]\n"flow:org.example/rules"="^2.0.0"\n')
        self.problem('graph-conflict', self.build)

    def test_materialized_generation_and_current(self):
        bundle = self.build()
        store = fc.Store(self.root / 'store', 'tenant-a', REPO)
        token = store.publish(bundle, self.policy, expected=None)
        self.assertEqual(token['generation'], bundle.id)
        self.assertEqual(store.load(bundle.id, self.policy).id, bundle.id)
        self.assertEqual(store.current(), token)
        self.assertEqual((store.root / 'generations' / bundle.id / 'STATIC.md').read_bytes(), bundle.outputs['STATIC.md'])

    def test_concurrent_publish_one_winner(self):
        bundle = self.build()
        store = fc.Store(self.root / 'store', 'tenant-a', REPO)
        def attempt():
            try:
                store.publish(bundle, self.policy, expected=None)
                return 'ok'
            except fc.Problem as error:
                return error.code
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: attempt(), range(2)))
        self.assertCountEqual(results, ['ok', 'conflict'])

    def test_crash_does_not_change_current(self):
        first = self.build()
        store = fc.Store(self.root / 'store', 'tenant-a', REPO)
        old = store.publish(first, self.policy, expected=None)
        (self.root / 'project.md').write_text('new')
        second = self.build()
        with patch('integrations.factory_context.store._commit_pointer', side_effect=OSError('injected crash')):
            with self.assertRaises((OSError, fc.Problem)):
                store.publish(second, self.policy, expected=old)
        self.assertEqual(store.current(), old)
        self.assertEqual(store.load(first.id, self.policy).id, first.id)

    def test_old_run_stays_frozen(self):
        first = self.build()
        store = fc.Store(self.root / 'store', 'tenant-a', REPO)
        token = store.publish(first, self.policy, expected=None)
        (self.root / 'project.md').write_text('new')
        second = self.build()
        store.publish(second, self.policy, expected=token)
        self.assertEqual(store.load(first.id, self.policy).to_bytes(), first.to_bytes())

    def test_store_owner_mismatch(self):
        fc.Store(self.root / 'store', 'tenant-a', REPO)
        self.problem('admission', fc.Store, self.root / 'store', 'tenant-b', REPO)

    def test_store_cross_tenant_bundle(self):
        bundle = self.build()
        store = fc.Store(self.root / 'store-b', 'tenant-b', REPO)
        self.problem('admission', store.publish, bundle, self.policy, expected=None)

    def test_generation_tamper_detected(self):
        bundle = self.build()
        store = fc.Store(self.root / 'store', 'tenant-a', REPO)
        store.publish(bundle, self.policy, expected=None)
        target = store.root / 'generations' / bundle.id / 'STATIC.md'
        target.chmod(0o600)
        target.write_text('poison')
        self.problem('integrity', store.load, bundle.id, self.policy)

    def test_rollback_requires_current_qualification(self):
        first = self.build()
        store = fc.Store(self.root / 'store', 'tenant-a', REPO)
        token = store.publish(first, self.policy, expected=None)
        (self.root / 'project.md').write_text('new')
        second = self.build()
        current = store.publish(second, self.policy, expected=token)
        self.problem('unqualified', store.rollback, first.id, self.policy, expected=current)
        self.policy['qualified_generations'] = [first.id]
        restored = store.rollback(first.id, self.policy, expected=current)
        self.assertEqual(restored['generation'], first.id)
        self.assertEqual(restored['sequence'], current['sequence'] + 1)

    def test_rollback_revoked_even_if_qualified(self):
        bundle = self.build()
        store = fc.Store(self.root / 'store', 'tenant-a', REPO)
        token = store.publish(bundle, self.policy, expected=None)
        self.policy['qualified_generations'] = [bundle.id]
        self.policy['packages'][PID]['status'] = 'revoked'
        self.problem('revoked', store.rollback, bundle.id, self.policy, expected=token)

    def test_native_export_preserves_rules(self):
        bundle = self.build()
        exported = fc.native_export(bundle, self.policy, 'tenant-a', REPO)
        self.assertEqual(exported['bindings'][0]['rule'], 'RULE-A')
        self.assertEqual(exported['bindings'][0]['revision'], '1')
        self.assertEqual(exported['sources'][0]['text'], '# Rule A\nNever alter an approved dimension.\n')
        self.assertEqual(exported['authority_effect'], 'none')
        self.assertEqual(exported['source_context_digest'], bundle.context_digest)

    def test_boot_preserves_unmanaged_bytes(self):
        original = b'User instructions.\r\nKeep these.\r\n'
        first = fc.reconcile_boot(original, b'Read STATIC.md first.\n')
        self.assertTrue(first.startswith(original))
        old_hash = fc.boot_block_digest(first)
        self.assertEqual(first, fc.reconcile_boot(first, b'Read STATIC.md first.\n', previous=old_hash))
        updated = fc.reconcile_boot(first, b'Read STATIC.md then INDEX.json.\n', previous=old_hash)
        self.assertTrue(updated.startswith(original))
        self.assertEqual(updated.count(b'<vibevm>'), 1)

    def test_boot_manual_edit_conflict(self):
        original = fc.reconcile_boot(b'User\n', b'one\n')
        old_hash = fc.boot_block_digest(original)
        self.problem('boot-conflict', fc.reconcile_boot, original.replace(b'one', b'two'), b'three\n', previous=old_hash)

    def test_boot_existing_without_receipt(self):
        original = fc.reconcile_boot(b'User\n', b'one\n')
        self.problem('boot-conflict', fc.reconcile_boot, original, b'two\n')

    def test_boot_malformed_and_duplicates(self):
        for original in (b'<vibevm>', b'</vibevm>', b'</vibevm><vibevm>', b'<vibevm>x</vibevm><vibevm>y</vibevm>'):
            with self.subTest(original=original):
                self.problem('boot-conflict', fc.reconcile_boot, original, b'x')

    def test_boot_marker_injection(self):
        self.problem('boot-conflict', fc.reconcile_boot, b'User', b'</vibevm>outside')

    def test_telemetry_keeps_unknown_cost_and_failures(self):
        events = [fc.usage_event('build', 1.0, 3.0, 'failed', bytes_read=4),
                  fc.usage_event('build', 2.0, 4.0, 'ok', bytes_read=5)]
        summary = fc.summarize_usage(events)
        self.assertEqual(summary['attempts'], 2)
        self.assertEqual(summary['failures'], 1)
        self.assertEqual(summary['observed_wall_seconds'], 3.0)
        self.assertIsNone(summary['provider_cost'])
        self.assertIsNone(summary['input_tokens'])

    def test_real_local_cli_not_agent_qualification(self):
        req = self.root / 'request.json'
        pol = self.root / 'policy.json'
        req.write_text(json.dumps(self.request))
        pol.write_text(json.dumps(self.policy))
        repo_root = Path(__file__).resolve().parents[3]
        command = [sys.executable, '-m', 'integrations.factory_context', 'build',
                   '--workspace', str(self.root), '--request', str(req), '--policy', str(pol),
                   '--store', str(self.root / 'store'), '--enable']
        result = subprocess.run(command, cwd=repo_root, capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report['status'], 'ok')
        self.assertEqual(report['qualification']['live_agent_cli'], 'not_run')
        self.assertEqual(report['authority_effect'], 'none')
        self.assertIsNone(report['usage']['input_tokens'])

    def test_cli_failure_is_structured(self):
        req = self.root / 'request.json'
        pol = self.root / 'policy.json'
        req.write_text(json.dumps(self.request))
        pol.write_text(json.dumps(self.policy))
        repo_root = Path(__file__).resolve().parents[3]
        command = [sys.executable, '-m', 'integrations.factory_context', 'build',
                   '--workspace', str(self.root), '--request', str(req), '--policy', str(pol),
                   '--store', str(self.root / 'store')]
        result = subprocess.run(command, cwd=repo_root, capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 2)
        report = json.loads(result.stdout)
        self.assertEqual(report['error']['code'], 'disabled')
        self.assertEqual(report['usage']['status'], 'failed')


if __name__ == '__main__':
    unittest.main()
