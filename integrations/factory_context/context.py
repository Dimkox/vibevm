"""Reproducible, caller-admitted context snapshots, not execution authority."""
from __future__ import annotations

import base64
import binascii
from dataclasses import replace
import hashlib
from pathlib import Path
import re
import sys
from typing import Any

from .boundary import (Limits, Problem, UPSTREAM, VERSION, canonical, checked_digest,
                       closed, decode_json, digest, identifier, parse_lock, read_file,
                       read_tree, safe_origin, safe_path, text, tree_hash,
                       validate_data, validate_manifest)

REQUEST_KEYS = {'schema_version', 'tenant', 'target_repository', 'change_id', 'route_id',
                'source_snapshot', 'change_spec_digest', 'upstream_commit', 'lock_path',
                'manifest_path', 'packages', 'facts', 'settings', 'sources', 'bindings'}
POLICY_KEYS = {'schema_version', 'tenant', 'target_repository', 'packages', 'rules',
               'audit_allowed', 'qualified_generations', 'required_sources', 'required_bindings'}
SOURCE_KEYS = {'id', 'package', 'path', 'mandatory', 'scope', 'reason', 'when'}
BINDING_KEYS = {'criterion', 'source', 'repository', 'rule', 'revision', 'digest', 'relation', 'mandatory'}


def _schema_version(value: dict) -> None:
    if type(value['schema_version']) is not int or value['schema_version'] != 1:
        raise Problem('schema', 'unsupported adapter schema')


def _repository(value: Any) -> str:
    value = text(value, 'repository', 256)
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', value):
        raise Problem('schema', 'repository must have an explicit owner/name identity')
    return value


def validate_request(request: dict, limits: Limits) -> dict:
    if len(canonical(request)) > limits.max_file_bytes:
        raise Problem('bounds', 'request exceeds limit')
    closed(request, REQUEST_KEYS)
    _schema_version(request)
    for key in ('tenant', 'change_id', 'route_id'):
        identifier(request[key])
    _repository(request['target_repository'])
    closed(request['source_snapshot'], {'commit', 'tree_digest'})
    if not re.fullmatch(r'(?:[0-9a-f]{40}|[0-9a-f]{64})', text(request['source_snapshot']['commit'])):
        raise Problem('schema', 'caller source snapshot requires an immutable commit identity')
    checked_digest(request['source_snapshot']['tree_digest'])
    checked_digest(request['change_spec_digest'])
    if request['upstream_commit'] != UPSTREAM:
        raise Problem('unqualified', 'upstream/parser profile has not been qualified')
    safe_path(request['lock_path'], limits.max_depth)
    safe_path(request['manifest_path'], limits.max_depth)
    closed(request['settings'], {'dialect', 'overrides'})
    if request['settings']['dialect'] != 'markdown':
        raise Problem('unqualified', 'only explicit Markdown output is supported')
    if request['settings']['overrides'] != {}:
        raise Problem('graph-conflict', 'overrides must be resolved and approved upstream, not applied here')
    if type(request['packages']) is not dict or len(request['packages']) > limits.max_packages:
        raise Problem('bounds', 'invalid package directory map')
    for relative in request['packages'].values():
        safe_path(relative, limits.max_depth)
    facts = request['facts']
    if type(facts) is not dict or len(facts) > limits.max_files:
        raise Problem('bounds', 'invalid fact map')
    for key, value in facts.items():
        identifier(key)
        if type(value) not in (str, bool, int) or (type(value) is str and len(value) > 1024):
            raise Problem('schema', 'facts must be bounded scalar values')
    sources = request['sources']
    if type(sources) is not list or len(sources) > limits.max_files:
        raise Problem('bounds', 'invalid sources')
    seen = set()
    for source in sources:
        closed(source, SOURCE_KEYS)
        identifier(source['id'])
        if source['id'] in seen:
            raise Problem('schema', 'duplicate source ID')
        seen.add(source['id'])
        safe_path(source['path'], limits.max_depth)
        if source['package'] is not None and type(source['package']) is not str:
            raise Problem('schema', 'package source must be a coordinate or null')
        if source['package'] is not None and source['package'] not in request['packages']:
            raise Problem('missing-package', 'source package is not explicitly supplied')
        if type(source['mandatory']) is not bool:
            raise Problem('schema', 'mandatory must be a boolean')
        text(source['scope'], 'scope')
        text(source['reason'], 'inclusion reason')
        if source['when'] is not None:
            condition = closed(source['when'], {'fact', 'equals'})
            identifier(condition['fact'])
            if (type(condition['equals']) not in (str, bool, int)
                    or (type(condition['equals']) is str and len(condition['equals']) > 1024)):
                raise Problem('schema', 'unsupported condition operand')
    if type(request['bindings']) is not list or len(request['bindings']) > limits.max_files:
        raise Problem('bounds', 'invalid bindings')
    return request


def validate_policy(policy: dict, tenant: str, repository: str, limits: Limits) -> None:
    if len(canonical(policy)) > limits.max_file_bytes:
        raise Problem('bounds', 'policy exceeds limit')
    closed(policy, POLICY_KEYS)
    _schema_version(policy)
    if policy['tenant'] != tenant or policy['target_repository'] != repository:
        raise Problem('admission', 'policy does not belong to this tenant/repository')
    if type(policy['audit_allowed']) is not bool:
        raise Problem('schema', 'audit_allowed must be a boolean')
    if type(policy['packages']) is not dict or len(policy['packages']) > limits.max_packages:
        raise Problem('bounds', 'policy package bounds exceeded')
    if type(policy['rules']) is not dict or len(policy['rules']) > limits.max_files:
        raise Problem('bounds', 'policy rule bounds exceeded')
    if type(policy['qualified_generations']) is not list or len(policy['qualified_generations']) > limits.max_files:
        raise Problem('bounds', 'qualification list bounds exceeded')
    for generation in policy['qualified_generations']:
        if type(generation) is not str or not re.fullmatch(r'[0-9a-f]{64}', generation):
            raise Problem('schema', 'invalid qualified generation identity')
    for key in ('required_sources', 'required_bindings'):
        if type(policy[key]) is not list or len(policy[key]) > limits.max_files:
            raise Problem('bounds', 'mandatory admission inventory exceeds bounds')
    seen_sources = set()
    for source in policy['required_sources']:
        closed(source, {'id', 'package', 'path', 'digest'})
        identifier(source['id'])
        if source['id'] in seen_sources:
            raise Problem('schema', 'duplicate mandatory source identity')
        seen_sources.add(source['id'])
        if source['package'] is not None and type(source['package']) is not str:
            raise Problem('schema', 'invalid mandatory package source')
        safe_path(source['path'], limits.max_depth)
        checked_digest(source['digest'])
    for binding in policy['required_bindings']:
        closed(binding, BINDING_KEYS - {'mandatory'})
        for key, value in binding.items():
            text(value, key)
        _repository(binding['repository'])
        checked_digest(binding['digest'])
    for grant in policy['packages'].values():
        closed(grant, {'content_hash', 'origin', 'repository', 'ref', 'status', 'license'})
        checked_digest(grant['content_hash'], tree=True)
        safe_origin(grant['origin'])
        _repository(grant['repository'])
        if not re.fullmatch(r'(?:[0-9a-f]{40}|[0-9a-f]{64})', text(grant['ref'])):
            raise Problem('admission', 'authoritative package source must have an immutable ref')
        if type(grant['status']) is not str or grant['status'] not in {'active', 'revoked', 'draft'}:
            raise Problem('schema', 'unknown package admission status')
        if type(grant['license']) is not str:
            raise Problem('license', 'license identity is required')
    for rule in policy['rules'].values():
        closed(rule, {'revision', 'digest', 'status'})
        text(rule['revision'], 'rule revision')
        checked_digest(rule['digest'])
        if type(rule['status']) is not str or rule['status'] not in {'active', 'revoked', 'draft'}:
            raise Problem('schema', 'unknown rule admission status')


def builder_identity() -> dict:
    """Identity the actual adapter sources and parser runtime, never a caller label."""
    root = Path(__file__).parent
    hasher = hashlib.sha256()
    for file in sorted(root.glob('*.py')):
        hasher.update(file.name.encode() + b'\0' + file.read_bytes() + b'\0')
    return {'name': 'vibevm-factory-context-data-only', 'version': VERSION,
            'source_digest': 'sha256:' + hasher.hexdigest(), 'upstream_commit': UPSTREAM,
            'parser': 'python-tomllib', 'runtime': sys.implementation.name + '-' + '.'.join(map(str, sys.version_info[:2])),
            'tree_profile': 'posix-normalized', 'output_dialect': 'markdown'}


class Bundle:
    """An immutable serialized snapshot. Constructing it does not admit it."""

    def __init__(self, value: dict):
        self._raw = canonical(value)

    @classmethod
    def from_bytes(cls, raw: bytes, limits: Limits = Limits()) -> 'Bundle':
        return cls(decode_json(raw, limits.max_total_bytes * 4))

    @property
    def value(self) -> dict:
        return decode_json(self._raw)

    @property
    def id(self) -> str:
        return hashlib.sha256(self._raw).hexdigest()

    @property
    def context_digest(self) -> str:
        return self.value['manifest']['context_digest']

    @property
    def outputs(self) -> dict[str, bytes]:
        value = self.value
        objects = value['objects']
        return {name: base64.b64decode(objects[ref], validate=True)
                for name, ref in value['manifest']['semantic']['outputs'].items()}

    def to_bytes(self) -> bytes:
        return self._raw


def _admit_package(package: dict, policy: dict, audit: bool = False) -> dict:
    grant = policy['packages'].get(package['id'])
    if grant is None:
        raise Problem('admission', 'package is not admitted: ' + package['id'])
    if grant['origin'] != package['source_url']:
        raise Problem('origin', 'package origin is not admitted: ' + package['id'])
    if grant['content_hash'] != package['content_hash']:
        raise Problem('integrity', 'policy and lock disagree on package content')
    if grant['status'] != 'active' and not (audit and policy['audit_allowed'] and grant['status'] == 'revoked'):
        raise Problem('revoked', 'package is not active: ' + package['id'])
    if not grant['license'] or grant['license'].lower() in {'unknown', 'noassertion', 'none'}:
        raise Problem('license', 'package license has not been admitted')
    return grant


def _current_package(package: dict, files: dict[str, bytes], policy: dict, audit: bool, limits: Limits) -> dict:
    grant = _admit_package(package, policy, audit)
    label = package['content_hash'].rsplit(':', 1)[0] + ':'
    if tree_hash(files, label) != package['content_hash']:
        raise Problem('integrity', 'package bytes do not match frozen identity: ' + package['id'])
    if 'vibe.toml' not in files:
        raise Problem('missing-source', 'package authored manifest is missing')
    metadata = validate_manifest(files['vibe.toml'], package=package, limits=limits)['package']
    if metadata['license'] != grant['license']:
        raise Problem('license', 'authored and admitted license identities differ')
    return grant


def _bindings(request: dict, decisions: list[dict], source_bytes: dict[str, bytes], policy: dict, audit: bool) -> list[dict]:
    selected = {item['id']: item for item in decisions if item['included']}
    sources = {item['id']: item for item in request['sources']}
    result = []
    seen = set()
    for binding in request['bindings']:
        closed(binding, BINDING_KEYS)
        for key in ('criterion', 'source', 'rule', 'revision'):
            text(binding[key], key)
        _repository(binding['repository'])
        checked_digest(binding['digest'])
        if type(binding['mandatory']) is not bool:
            raise Problem('schema', 'binding mandatory must be a boolean')
        key = (binding['repository'], binding['rule'], binding['criterion'])
        if key in seen:
            raise Problem('mapping', 'duplicate canonical criterion binding')
        seen.add(key)
        if type(binding['relation']) is not str:
            raise Problem('schema', 'mapping relation must be a string')
        status = 'mapped'
        rule = policy['rules'].get(binding['repository'] + '#' + binding['rule'])
        source = sources.get(binding['source'])
        if binding['relation'] not in {'implements', 'verifies', 'documents', 'deviates', 'informs'}:
            status = 'unqualified'
        elif binding['source'] not in selected or rule is None or source is None:
            status = 'broken'
        else:
            owner = request['target_repository'] if source['package'] is None else policy['packages'][source['package']]['repository']
            allowed = rule['status'] == 'active' or (audit and policy['audit_allowed'] and rule['status'] == 'revoked')
            if (not allowed or owner != binding['repository'] or rule['revision'] != binding['revision']
                    or rule['digest'] != binding['digest'] or digest(source_bytes[binding['source']]) != binding['digest']):
                status = 'stale'
        if binding['mandatory'] and status != 'mapped':
            raise Problem('mapping', status + ' mandatory binding: ' + binding['criterion'])
        result.append({**binding, 'status': status})
    return result


def _minimum(decisions: list[dict], bindings: list[dict], policy: dict) -> None:
    selected = {source['id']: source for source in decisions}
    for required in policy['required_sources']:
        source = selected.get(required['id'])
        if (source is None or not source['mandatory'] or not source['included']
                or any(source[key] != value for key, value in required.items())):
            raise Problem('mapping', 'current policy mandatory source is missing or changed')
    order = [source['id'] for source in decisions if source['included'] and source['mandatory']]
    required_order = [source['id'] for source in policy['required_sources']]
    if order[:len(required_order)] != required_order:
        raise Problem('mapping', 'mandatory prefix order differs from current policy')
    for required in policy['required_bindings']:
        if not any(binding['mandatory'] and binding['status'] == 'mapped'
                   and all(binding[key] == value for key, value in required.items()) for binding in bindings):
            raise Problem('mapping', 'current policy mandatory binding is missing or changed')


def _compose(request: dict, policy: dict, lock_raw: bytes, authored: bytes,
             packages: dict[str, dict[str, bytes]], project: dict[str, bytes],
             limits: Limits, audit: bool = False) -> Bundle:
    validate_request(request, limits)
    validate_policy(policy, request['tenant'], request['target_repository'], limits)
    if audit and not policy['audit_allowed']:
        raise Problem('admission', 'historical audit is not authorized')
    graph = parse_lock(lock_raw, limits)
    validate_manifest(authored, roots=graph['roots'], limits=limits)
    ids = {package['id'] for package in graph['packages']}
    if ids != request['packages'].keys() or ids != packages.keys():
        raise Problem('missing-package', 'supplied directories do not match the complete frozen graph')
    objects: dict[str, str] = {}
    captured_files = 0
    captured_bytes = 0

    def capture(raw: bytes) -> str:
        nonlocal captured_files, captured_bytes
        ref = digest(raw)
        if ref not in objects:
            captured_files += 1
            captured_bytes += len(raw)
            if captured_files > limits.max_files * 4 or captured_bytes > limits.max_total_bytes * 3:
                raise Problem('bounds', 'snapshot aggregate bounds exceeded')
            objects[ref] = base64.b64encode(raw).decode('ascii')
        return ref

    package_refs = {}
    provenance = {}
    input_count = len(project) + sum(len(files) for files in packages.values()) + 2
    input_size = sum(map(len, project.values())) + sum(len(raw) for files in packages.values() for raw in files.values()) + len(lock_raw) + len(authored)
    if input_count > limits.max_files or input_size > limits.max_total_bytes:
        raise Problem('bounds', 'combined inputs exceed snapshot bounds')
    for package in graph['packages']:
        files = packages[package['id']]
        for name, raw in files.items():
            safe_path(name, limits.max_depth)
            validate_data(name, raw, limits)
        grant = _current_package(package, files, policy, audit, limits)
        provenance[package['id']] = {key: grant[key] for key in ('origin', 'repository', 'ref', 'license')}
        package_refs[package['id']] = {name: capture(raw) for name, raw in sorted(files.items())}
    project_refs = {}
    for path, raw in sorted(project.items()):
        safe_path(path, limits.max_depth)
        validate_data(path, raw, limits)
        project_refs[path] = capture(raw)
    decisions = []
    source_bytes = {}
    outputs: dict[str, bytes] = {}
    output_bytes = 0

    def output(name: str, raw: bytes) -> None:
        nonlocal output_bytes
        output_bytes += len(raw)
        if output_bytes > limits.max_total_bytes * 3:
            raise Problem('bounds', 'logical output bytes exceed limit')
        outputs[name] = raw

    for source in request['sources']:
        files = project if source['package'] is None else packages[source['package']]
        if source['path'] not in files:
            raise Problem('missing-source', 'selected source is missing: ' + source['id'])
        raw = files[source['path']]
        source_bytes[source['id']] = raw
        condition = source['when']
        state = 'true'
        if condition is not None:
            if condition['fact'] not in request['facts']:
                state = 'unknown'
            else:
                value = request['facts'][condition['fact']]
                state = 'true' if type(value) is type(condition['equals']) and value == condition['equals'] else 'false'
        included = state == 'true' or (state == 'unknown' and source['mandatory'])
        path = 'sources/' + source['id'] + Path(source['path']).suffix.lower()
        decisions.append({**source, 'condition': state, 'included': included,
                          'digest': capture(raw), 'mode': 'full', 'output_path': path})
        if included:
            output(path, raw)
    bindings = _bindings(request, decisions, source_bytes, policy, audit)
    _minimum(decisions, bindings, policy)
    mandatory = [item for item in decisions if item['mandatory'] and item['included']]
    optional = [item for item in decisions if not item['mandatory'] and item['included']]
    chunks = [b'# Mandatory project context\n\n']
    prefix_size = len(chunks[0])
    for item in mandatory:
        chunk = ('## Source: ' + item['id'] + '\n\n').encode() + source_bytes[item['id']] + b'\n\n'
        prefix_size += len(chunk)
        if prefix_size + output_bytes > limits.max_total_bytes * 3:
            raise Problem('bounds', 'mandatory prefix exceeds output budget')
        chunks.append(chunk)
    output('STATIC.md', b''.join(chunks))
    output('INDEX.json', canonical({'schema_version': 1, 'boot_order': ['STATIC.md'] + [item['output_path'] for item in optional],
                                       'sources': decisions}))
    output('bindings.json', canonical(bindings))
    semantic = {'schema_version': 1, 'builder': builder_identity(), 'request': request,
                'mandatory_policy': {key: policy[key] for key in ('required_sources', 'required_bindings')},
                'resolved_graph': graph, 'provenance': provenance, 'authored_manifest_digest': capture(authored),
                'package_files': package_refs, 'project_files': project_refs, 'decisions': decisions,
                'rule_bindings': bindings, 'outputs': {name: capture(raw) for name, raw in sorted(outputs.items())}}
    manifest = {'schema_version': 1, 'semantic': semantic, 'context_digest': digest(canonical(semantic)),
                'transport': {'raw_lock_digest': capture(lock_raw)}, 'authority_effect': 'none'}
    bundle = Bundle({'schema_version': 1, 'manifest': manifest, 'objects': objects})
    if len(bundle.to_bytes()) > limits.max_total_bytes * 4:
        raise Problem('bounds', 'serialized bundle exceeds limit')
    return bundle


def build(workspace: Path, request: dict, policy: dict, *, enabled: bool = False,
          limits: Limits = Limits()) -> Bundle:
    if enabled is not True:
        raise Problem('disabled', 'the optional data-only adapter is disabled')
    # Detach mutable caller objects before collecting any source bytes.
    request = decode_json(canonical(request))
    policy = decode_json(canonical(policy))
    validate_request(request, limits)
    validate_policy(policy, request['tenant'], request['target_repository'], limits)
    workspace = Path(workspace)
    lock_raw = read_file(workspace, request['lock_path'], limits)
    authored = read_file(workspace, request['manifest_path'], limits)
    graph = parse_lock(lock_raw, limits)
    if {item['id'] for item in graph['packages']} != request['packages'].keys():
        raise Problem('missing-package', 'complete package graph must be explicitly supplied')
    validate_manifest(authored, roots=graph['roots'], limits=limits)
    for package in graph['packages']:
        _admit_package(package, policy)
    count = 2
    size = len(lock_raw) + len(authored)

    def remaining() -> Limits:
        if count >= limits.max_files or size >= limits.max_total_bytes:
            raise Problem('bounds', 'combined input budget exhausted')
        return replace(limits, max_files=limits.max_files - count,
                       max_total_bytes=limits.max_total_bytes - size,
                       max_file_bytes=min(limits.max_file_bytes, limits.max_total_bytes - size))

    packages = {}
    for key, path in request['packages'].items():
        files = read_tree(workspace / path, remaining())
        count += len(files)
        size += sum(map(len, files.values()))
        packages[key] = files
    project = {}
    for source in request['sources']:
        if source['package'] is None and source['path'] not in project:
            raw = read_file(workspace, source['path'], remaining())
            count += 1
            size += len(raw)
            project[source['path']] = raw
    return _compose(request, policy, lock_raw, authored, packages, project, limits)


def replay(bundle: Bundle, policy: dict, tenant: str, repository: str, *, audit: bool = False,
           limits: Limits = Limits()) -> Bundle:
    """Rebuild solely from retained bytes, checking current caller policy again."""
    if len(bundle.to_bytes()) > limits.max_total_bytes * 4:
        raise Problem('bounds', 'serialized snapshot exceeds limit')
    value = closed(bundle.value, {'schema_version', 'manifest', 'objects'})
    _schema_version(value)
    manifest = closed(value['manifest'], {'schema_version', 'semantic', 'transport', 'context_digest', 'authority_effect'})
    _schema_version(manifest)
    if manifest['authority_effect'] != 'none':
        raise Problem('admission', 'snapshot cannot grant authority')
    semantic = closed(manifest['semantic'], {'schema_version', 'builder', 'request', 'resolved_graph', 'provenance',
                       'authored_manifest_digest', 'package_files', 'project_files', 'decisions', 'rule_bindings', 'outputs', 'mandatory_policy'})
    _schema_version(semantic)
    closed(manifest['transport'], {'raw_lock_digest'})
    if digest(canonical(semantic)) != checked_digest(manifest['context_digest']):
        raise Problem('integrity', 'semantic snapshot digest mismatch')
    request = validate_request(semantic['request'], limits)
    if request['tenant'] != tenant or request['target_repository'] != repository:
        raise Problem('admission', 'snapshot belongs to a different tenant/repository')
    validate_policy(policy, tenant, repository, limits)
    if semantic['builder'] != builder_identity():
        raise Problem('unqualified', 'snapshot requires a different exact adapter/parser build')
    encoded = value['objects']
    if type(encoded) is not dict or len(encoded) > limits.max_files * 4:
        raise Problem('bounds', 'object count exceeds limit')
    objects = {}
    total = 0
    for ref, data in encoded.items():
        checked_digest(ref)
        if type(data) is not str or len(data) > limits.max_total_bytes * 4:
            raise Problem('bounds', 'encoded object exceeds limit')
        try:
            raw = base64.b64decode(data, validate=True)
        except (ValueError, binascii.Error) as error:
            raise Problem('encoding', 'invalid retained object encoding') from error
        total += len(raw)
        if total > limits.max_total_bytes * 3:
            raise Problem('bounds', 'retained objects exceed aggregate limit')
        if digest(raw) != ref:
            raise Problem('integrity', 'retained object content mismatch')
        objects[ref] = raw

    def get(ref: str) -> bytes:
        checked_digest(ref)
        if ref not in objects:
            raise Problem('missing-object', 'required retained object is unavailable')
        return objects[ref]

    if type(semantic['package_files']) is not dict or type(semantic['project_files']) is not dict:
        raise Problem('schema', 'invalid retained file map')
    packages = {}
    for key, refs in semantic['package_files'].items():
        if type(refs) is not dict:
            raise Problem('schema', 'invalid package file map')
        packages[key] = {path: get(ref) for path, ref in refs.items()}
    project = {path: get(ref) for path, ref in semantic['project_files'].items()}
    rebuilt = _compose(request, policy, get(manifest['transport']['raw_lock_digest']),
                       get(semantic['authored_manifest_digest']), packages, project, limits, audit)
    if rebuilt.to_bytes() != bundle.to_bytes():
        raise Problem('integrity', 'snapshot cannot be reproduced from its complete retained inputs')
    return rebuilt


def native_export(bundle: Bundle, policy: dict, tenant: str, repository: str, *, audit: bool = False,
                  limits: Limits = Limits()) -> dict:
    checked = replay(bundle, policy, tenant, repository, audit=audit, limits=limits)
    semantic = checked.value['manifest']['semantic']
    outputs = checked.outputs
    sources = []
    for source in semantic['decisions']:
        if not source['included']:
            continue
        owner = repository if source['package'] is None else semantic['provenance'][source['package']]['repository']
        sources.append({'id': source['id'], 'repository': owner, 'path': source['path'],
                        'digest': source['digest'], 'mandatory': source['mandatory'],
                        'scope': source['scope'], 'reason': source['reason'],
                        'text': outputs[source['output_path']].decode('utf-8')})
    return {'schema_version': 1, 'source_generation': checked.id,
            'source_context_digest': checked.context_digest, 'sources': sources,
            'bindings': semantic['rule_bindings'], 'authority_effect': 'none',
            'purpose': 'audit_only' if audit else 'native_rebuild_input',
            'requires_new_snapshot_and_external_gates': True}
