"""Boundary regression probes; these are not live-agent qualification evidence."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from integrations import factory_context as fc
from integrations.factory_context import boundary, context
from integrations.factory_context.tests.test_adapter import fixture, PID, REPO, sha


class RegressionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.request, self.policy = fixture(self.root)

    def build(self, **kw):
        return fc.build(self.root, self.request, self.policy, enabled=True, **kw)

    def problem(self, code, callback, *args, **kw):
        with self.assertRaises(fc.Problem) as caught:
            callback(*args, **kw)
        self.assertEqual(caught.exception.code, code)

    def test_revoked_package_is_refused_before_read(self):
        self.policy['packages'][PID]['status'] = 'revoked'
        with patch.object(context, 'read_tree', side_effect=AssertionError('unauthorized read')):
            self.problem('revoked', self.build)

    def test_origin_refused_before_read(self):
        self.policy['packages'][PID]['origin'] = 'https://other.example/rules'
        with patch.object(context, 'read_tree', side_effect=AssertionError('unauthorized read')):
            self.problem('origin', self.build)

    def test_unknown_package_refused_before_read(self):
        self.policy['packages'] = {}
        with patch.object(context, 'read_tree', side_effect=AssertionError('unauthorized read')):
            self.problem('admission', self.build)

    def test_global_input_budget_is_passed_to_reader(self):
        total = 2500
        actual = context.read_tree
        def check(root, limits):
            self.assertLess(limits.max_total_bytes, total)
            self.assertLess(limits.max_files, 20)
            return actual(root, limits)
        with patch.object(context, 'read_tree', side_effect=check):
            self.build(limits=fc.Limits(max_total_bytes=total, max_files=20))

    def test_repeated_source_output_amplification_is_bounded(self):
        (self.root / 'project.md').write_bytes(b'x' * 4096)
        self.request['sources'] = [dict(id=f'copy-{i}', package=None, path='project.md', mandatory=True,
                                        scope='all', reason='required', when=None) for i in range(50)]
        self.request['bindings'] = []
        self.policy['required_sources'] = []
        self.policy['required_bindings'] = []
        self.problem('bounds', self.build, limits=fc.Limits(max_total_bytes=12000))

    def test_mixed_dependency_values_fail_closed(self):
        path = self.root / 'vibe.lock'
        path.write_text(path.read_text().replace('dependencies=[]', 'dependencies=[1,"flow:org.example/rules@=1.0.0"]'))
        self.problem('schema', self.build)

    def test_root_manifest_unknown_package_field_is_rejected(self):
        path = self.root / 'vibe.toml'
        path.write_text(path.read_text() + '\n[package]\nscripts=["effect"]\n')
        self.problem('schema', self.build)

    def test_authored_constraint_can_match_frozen_transitive_edge(self):
        raw = (b'[package]\nkind="flow"\nname="rules"\ngroup="org.example"\n'
               b'version="1.0.0"\nlicense="UPL-1.0"\n[requires.packages]\n'
               b'"flow:org.example/child"="^1.0.0"\n')
        package = dict(kind='flow', name='rules', group='org.example', version='1.0.0',
                       dependencies=['flow:org.example/child@=1.2.0'])
        boundary.validate_manifest(raw, package=package)
        package['dependencies'] = ['flow:org.example/child@=2.0.0']
        self.problem('graph-conflict', boundary.validate_manifest, raw, package=package)

    def test_git_metadata_is_rejected_before_open(self):
        (self.root / '.git').mkdir()
        (self.root / '.git/config').write_text('credentials here')
        with patch.object(boundary, '_read_at', side_effect=AssertionError('secret metadata read')):
            self.problem('path', boundary.read_file, self.root, '.git/config')

    def test_unsupported_extension_is_rejected_before_open(self):
        (self.root / 'binary.bin').write_bytes(b'opaque bytes')
        with patch.object(boundary, '_read_at', side_effect=AssertionError('unsupported file read')):
            self.problem('executable-content', boundary.read_file, self.root, 'binary.bin')

    def test_expected_pointer_rejects_boolean_sequence(self):
        bundle = self.build()
        store = fc.Store(self.root / 'store', 'tenant-a', REPO)
        current = store.publish(bundle, self.policy, expected=None)
        self.problem('schema', store.publish, bundle, self.policy,
                     expected={'generation': current['generation'], 'sequence': True})

    def test_idempotent_publish_does_not_increment_same_generation(self):
        bundle = self.build()
        store = fc.Store(self.root / 'store', 'tenant-a', REPO)
        current = store.publish(bundle, self.policy, expected=None)
        repeated = store.publish(bundle, self.policy, expected=current)
        self.assertEqual(current, repeated)

    def test_telemetry_rejects_different_monotonic_domains(self):
        first = fc.usage_event('build', 1, 3, 'ok')
        second = fc.usage_event('build', 1, 2, 'ok')
        first['clock_domain'] = 'host-a'
        second['clock_domain'] = 'host-b'
        self.problem('clock-domain', fc.summarize_usage, [first, second])

    def test_bad_origin_is_structured(self):
        self.problem('origin', boundary.safe_origin, 'https://[malformed')

    def test_unhashable_status_is_structured(self):
        self.policy['packages'][PID]['status'] = []
        self.problem('schema', self.build)

    def test_unhashable_source_package_is_structured(self):
        self.request['sources'][0]['package'] = []
        self.problem('schema', self.build)

    def test_bad_relation_is_structured(self):
        self.request['bindings'][0]['relation'] = []
        self.problem('schema', self.build)

    def test_condition_string_is_bounded(self):
        self.request['sources'][0]['when'] = {'fact': 'absent', 'equals': 'a' * 2048}
        self.problem('schema', self.build)

    def test_cli_does_not_label_bundle_size_as_total_write_io(self):
        (self.root / 'request.json').write_text(json.dumps(self.request))
        (self.root / 'policy.json').write_text(json.dumps(self.policy))
        command = [sys.executable, '-m', 'integrations.factory_context', 'build',
                   '--request', str(self.root / 'request.json'), '--workspace', str(self.root),
                   '--policy', str(self.root / 'policy.json'), '--store', str(self.root / 'store'), '--enable']
        result = subprocess.run(command, cwd=Path(__file__).resolve().parents[3], capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertIsNone(report['usage']['bytes_written'])
        self.assertGreater(report['snapshot_serialized_bytes'], 0)

    def test_policy_required_source_cannot_be_omitted(self):
        self.request['sources'] = self.request['sources'][1:]
        self.request['bindings'] = []
        self.problem('mapping', self.build)

    def test_policy_required_binding_cannot_be_omitted(self):
        self.request['bindings'] = []
        self.problem('mapping', self.build)

    def test_policy_required_source_cannot_be_demoted(self):
        self.request['sources'][0]['mandatory'] = False
        self.problem('mapping', self.build)

    def test_policy_required_binding_cannot_be_demoted(self):
        self.request['bindings'][0]['mandatory'] = False
        self.problem('mapping', self.build)

    def test_policy_required_source_digest_is_checked(self):
        self.policy['required_sources'][0]['digest'] = sha(b'different required text')
        self.problem('mapping', self.build)

    def test_manifest_credential_url_is_rejected(self):
        path = self.root / 'vibe.toml'
        path.write_text(path.read_text() + '\n[package]\nkind="flow"\nname="root"\ngroup="org.example"\nversion="1.0.0"\nlicense="UPL-1.0"\nhomepage="https://user:password@example.org/x"\n')
        self.problem('origin', self.build)

    def test_real_cli_replay_and_native_export(self):
        (self.root / 'request.json').write_text(json.dumps(self.request))
        (self.root / 'policy.json').write_text(json.dumps(self.policy))
        prefix = [sys.executable, '-m', 'integrations.factory_context']
        common = ['--policy', str(self.root / 'policy.json'), '--store', str(self.root / 'store'), '--enable']
        def run(arguments):
            result = subprocess.run(prefix + arguments + common, cwd=Path(__file__).resolve().parents[3],
                                    capture_output=True, text=True, timeout=20)
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            return json.loads(result.stdout)
        built = run(['build', '--request', str(self.root / 'request.json'), '--workspace', str(self.root)])
        scope = ['--generation', built['generation'], '--tenant', 'tenant-a', '--repository', REPO]
        recovered = run(['replay'] + scope)
        exported = run(['export'] + scope)
        self.assertEqual(recovered['context_digest'], built['context_digest'])
        self.assertEqual(exported['native']['bindings'][0]['rule'], 'RULE-A')
        self.assertEqual(exported['native']['bindings'][0]['status'], 'mapped')
        self.assertTrue(exported['native']['requires_new_snapshot_and_external_gates'])
        self.assertEqual(exported['qualification']['live_agent_cli'], 'not_run')

    def test_same_boot_order_is_required_by_policy(self):
        self.request['sources'][1]['mandatory'] = True
        self.request['sources'].reverse()
        self.problem('mapping', self.build)

    def test_process_race_has_one_publisher(self):
        (self.root / 'request.json').write_text(json.dumps(self.request))
        (self.root / 'policy.json').write_text(json.dumps(self.policy))
        command = [sys.executable, '-m', 'integrations.factory_context', 'build',
                   '--request', str(self.root / 'request.json'), '--workspace', str(self.root),
                   '--policy', str(self.root / 'policy.json'), '--store', str(self.root / 'store'), '--enable']
        processes = [subprocess.Popen(command, cwd=Path(__file__).resolve().parents[3], stdout=subprocess.PIPE,
                                      stderr=subprocess.PIPE, text=True) for _ in range(2)]
        results = [p.communicate(timeout=20) for p in processes]
        self.assertEqual(sorted(p.returncode for p in processes), [0, 2], results)
        reports = [json.loads(out) for out, _ in results]
        self.assertEqual([r['error']['code'] for r in reports if r['status'] == 'blocked'], ['conflict'])


if __name__ == '__main__':
    unittest.main()
