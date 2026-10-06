"""Bounded data reads and validation of an already-resolved VibeVM graph.

No resolver, installer, shell, archive extraction, network or agent is invoked.
Tree hashing follows the pinned upstream recipe on normalized POSIX paths.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, replace
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import tomllib
from typing import Any, Iterator
from urllib.parse import urlsplit
import xml.etree.ElementTree as ET

UPSTREAM = '30d217bfce47bcaccadabd9468f00e315dbcfead'
VERSION = '0.1.0'
EXCLUDES = frozenset({'.git', '.vibe', 'target', 'node_modules', '.vibeignore'})
SUFFIXES = frozenset({'.md', '.txt', '.xml', '.json', '.toml', '.lock'})


class Problem(ValueError):
    """A named, fail-closed refusal. Messages must not include source contents."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class Limits:
    max_file_bytes: int = 1024 * 1024
    max_total_bytes: int = 16 * 1024 * 1024
    max_files: int = 1024
    max_depth: int = 16
    max_packages: int = 128
    max_edges: int = 1024

    def __post_init__(self) -> None:
        if any(type(value) is not int or value <= 0 for value in vars(self).values()):
            raise Problem('bounds', 'limits must be positive integers')


def digest(raw: bytes) -> str:
    return 'sha256:' + hashlib.sha256(raw).hexdigest()


def canonical(value: Any) -> bytes:
    try:
        return json.dumps(value, sort_keys=True, separators=(',', ':'),
                          ensure_ascii=False, allow_nan=False).encode('utf-8')
    except (TypeError, ValueError, UnicodeError, RecursionError) as error:
        raise Problem('schema', 'value is not bounded JSON data') from error


def decode_json(raw: bytes, limit: int = 64 * 1024 * 1024) -> Any:
    if len(raw) > limit:
        raise Problem('bounds', 'JSON exceeds byte limit')

    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise Problem('schema', 'duplicate JSON key')
            result[key] = value
        return result

    def invalid_constant(_: str) -> None:
        raise Problem('schema', 'non-finite JSON value')

    try:
        return json.loads(raw.decode('utf-8'), object_pairs_hook=pairs,
                          parse_constant=invalid_constant)
    except (UnicodeError, ValueError, RecursionError) as error:
        if isinstance(error, Problem):
            raise
        raise Problem('schema', 'invalid JSON') from error


def closed(value: Any, required: set[str], optional: set[str] | None = None) -> dict:
    if type(value) is not dict or not required <= value.keys() or value.keys() - required - (optional or set()):
        raise Problem('schema', 'missing or unsupported fields')
    return value


def text(value: Any, label: str = 'identifier', limit: int = 1024) -> str:
    if (type(value) is not str or not value or len(value) > limit
            or any(ord(c) < 32 or ord(c) == 127 for c in value)):
        raise Problem('schema', 'invalid ' + label)
    try:
        value.encode('utf-8')
    except UnicodeError as error:
        raise Problem('encoding', 'invalid Unicode') from error
    return value


def identifier(value: Any) -> str:
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}', text(value)):
        raise Problem('schema', 'invalid short identifier')
    return value


def checked_digest(value: Any, tree: bool = False) -> str:
    pattern = r'(?:sha256|sha256-tree/1):[0-9a-f]{64}' if tree else r'sha256:[0-9a-f]{64}'
    if type(value) is not str or not re.fullmatch(pattern, value):
        raise Problem('digest', 'a full supported SHA-256 digest is required')
    return value


def safe_path(value: Any, max_depth: int = 16) -> str:
    if type(value) is not str or not value or len(value) > 2048:
        raise Problem('path', 'invalid relative path')
    parts = value.split('/')
    if len(parts) > max_depth:
        raise Problem('bounds', 'path exceeds depth limit')
    if (any(part in ('', '.', '..') for part in parts) or '\\' in value
            or ':' in value or '%' in value or any(ord(c) < 32 or ord(c) == 127 for c in value)):
        raise Problem('path', 'unsafe relative path')
    for part in parts:
        name = part.casefold()
        if (name.startswith('.env') or name in {'.ssh', '.aws', '.gnupg', 'credentials', 'id_rsa', 'id_ed25519'}
                or name.endswith(('.pem', '.key', '.p12', '.pfx'))):
            raise Problem('path', 'secret paths are not context sources')
    try:
        value.encode('utf-8')
    except UnicodeError as error:
        raise Problem('encoding', 'path is not UTF-8') from error
    return value


def safe_origin(value: Any) -> str:
    value = text(value, 'origin', 2048)
    try:
        parsed = urlsplit(value)
    except ValueError as error:
        raise Problem('origin', 'malformed origin locator') from error
    if (parsed.scheme not in {'https', 'file'} or parsed.username is not None
            or parsed.password is not None or parsed.query or parsed.fragment
            or (parsed.scheme == 'https' and not parsed.hostname)):
        raise Problem('origin', 'origin must be an explicit credential-free HTTPS or file locator')
    return value


@contextmanager
def directory(path: Path | str) -> Iterator[int]:
    """Open every component without following a symbolic link, including ancestors."""
    if not hasattr(os, 'O_NOFOLLOW') or os.name != 'posix':
        raise Problem('unqualified', 'this filesystem profile requires POSIX no-follow descriptors')
    absolute = Path(os.path.abspath(path))
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in absolute.parts[1:]:
            next_fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = next_fd
        yield fd
    except FileNotFoundError:
        raise
    except OSError as error:
        raise Problem('path', 'directory boundary refused') from error
    finally:
        os.close(fd)


def validate_filename(path: str) -> None:
    if any(part in EXCLUDES for part in path.split('/')):
        raise Problem('path', 'metadata and ambient caches are not explicit sources')
    if Path(path).suffix.lower() not in SUFFIXES and Path(path).name not in {'LICENSE', 'NOTICE', '.gitignore', '.gitattributes'}:
        raise Problem('executable-content', 'only declared text specification formats are supported')


def validate_data(path: str, raw: bytes, limits: Limits) -> None:
    validate_filename(path)
    if len(raw) > limits.max_file_bytes:
        raise Problem('bounds', 'file exceeds byte limit')
    try:
        decoded = raw.decode('utf-8')
    except UnicodeError as error:
        raise Problem('encoding', 'context data must be UTF-8') from error
    if '\x00' in decoded:
        raise Problem('encoding', 'NUL is not permitted in text data')
    if path.lower().endswith('.xml'):
        if re.search(r'<!\s*(DOCTYPE|ENTITY)|<\?xml-stylesheet', decoded, re.IGNORECASE):
            raise Problem('xml', 'DTD, entities and external stylesheets are forbidden')
        try:
            element = ET.fromstring(decoded)
            pending = [(element, 1)]
            count = 0
            while pending:
                node, depth = pending.pop()
                count += 1
                if depth > limits.max_depth * 4 or count > limits.max_files * 32:
                    raise Problem('bounds', 'XML structure exceeds bounds')
                if node.tag in {'{http://www.w3.org/2001/XInclude}include', '{http://www.w3.org/2001/XInclude}fallback'}:
                    raise Problem('xml', 'external include is forbidden')
                pending.extend((child, depth + 1) for child in node)
        except ET.ParseError as error:
            raise Problem('xml', 'malformed XML') from error


def _read_at(parent: int, name: str, limits: Limits) -> bytes:
    try:
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        try:
            before = os.fstat(fd)
            if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
                raise Problem('path', 'source must be an unlinked regular file, not a link or device')
            if before.st_size > limits.max_file_bytes:
                raise Problem('bounds', 'file exceeds byte limit')
            chunks = []
            remaining = limits.max_file_bytes + 1
            while remaining:
                block = os.read(fd, min(65536, remaining))
                if not block:
                    break
                chunks.append(block)
                remaining -= len(block)
            raw = b''.join(chunks)
            after = os.fstat(fd)
            if (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (after.st_size, after.st_mtime_ns, after.st_ctime_ns):
                raise Problem('conflict', 'source changed while being captured')
            if len(raw) > limits.max_file_bytes:
                raise Problem('bounds', 'file grew beyond byte limit')
            return raw
        finally:
            os.close(fd)
    except FileNotFoundError:
        raise
    except OSError as error:
        raise Problem('path', 'file boundary refused') from error


def read_file(root: Path, relative: str, limits: Limits = Limits()) -> bytes:
    safe_path(relative, limits.max_depth)
    validate_filename(relative)
    with directory(root) as root_fd:
        fd = os.dup(root_fd)
        try:
            parts = relative.split('/')
            for component in parts[:-1]:
                next_fd = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                os.close(fd)
                fd = next_fd
            raw = _read_at(fd, parts[-1], limits)
            validate_data(relative, raw, limits)
            return raw
        except FileNotFoundError as error:
            raise Problem('missing-source', 'required source is unavailable: ' + relative) from error
        except OSError as error:
            raise Problem('path', 'source boundary refused') from error
        finally:
            os.close(fd)


def read_tree(root: Path, limits: Limits = Limits()) -> dict[str, bytes]:
    files: dict[str, bytes] = {}
    folded: set[str] = set()
    visited = 0
    total = 0

    def walk(fd: int, prefix: str) -> None:
        nonlocal visited, total
        names = []
        with os.scandir(fd) as entries:
            for entry in entries:
                visited += 1
                if visited > limits.max_files * (limits.max_depth + 1):
                    raise Problem('bounds', 'tree enumeration exceeds limit')
                if entry.name not in EXCLUDES:
                    names.append(entry.name)
        for name in sorted(names):
            relative = safe_path(prefix + name, limits.max_depth)
            key = relative.casefold()
            if key in folded:
                raise Problem('path', 'case-folding path collision')
            folded.add(key)
            entry = os.stat(name, dir_fd=fd, follow_symlinks=False)
            if stat.S_ISDIR(entry.st_mode):
                child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                try:
                    walk(child, relative + '/')
                finally:
                    os.close(child)
            elif stat.S_ISREG(entry.st_mode) and entry.st_nlink == 1:
                validate_filename(relative)
                if len(files) >= limits.max_files or total >= limits.max_total_bytes:
                    raise Problem('bounds', 'package exceeds aggregate bounds')
                remaining = replace(limits, max_file_bytes=min(limits.max_file_bytes, limits.max_total_bytes - total))
                raw = _read_at(fd, name, remaining)
                validate_data(relative, raw, limits)
                total += len(raw)
                files[relative] = raw
                if len(files) > limits.max_files or total > limits.max_total_bytes:
                    raise Problem('bounds', 'package exceeds aggregate bounds')
            else:
                raise Problem('path', 'symlinks, hardlinks and special files are forbidden')
    try:
        with directory(root) as root_fd:
            walk(root_fd, '')
    except FileNotFoundError as error:
        raise Problem('missing-package', 'required package directory is unavailable') from error
    except OSError as error:
        raise Problem('path', 'package boundary refused') from error
    return files


def tree_hash(files: dict[str, bytes], label: str = 'sha256-tree/1:') -> str:
    if label not in {'sha256:', 'sha256-tree/1:'}:
        raise Problem('digest', 'unsupported tree hash recipe')
    hasher = hashlib.sha256()
    for name in sorted(files, key=lambda item: item.encode('utf-8')):
        safe_path(name)
        if any(part in EXCLUDES for part in name.split('/')):
            continue
        hasher.update(name.encode('utf-8') + b'\0' + files[name] + b'\0')
    return label + hasher.hexdigest()


def parse_toml(raw: bytes, limits: Limits = Limits()) -> dict:
    if len(raw) > limits.max_file_bytes:
        raise Problem('bounds', 'TOML exceeds limit')
    try:
        return tomllib.loads(raw.decode('utf-8'))
    except (ValueError, UnicodeError, RecursionError) as error:
        raise Problem('schema', 'invalid TOML') from error


def version(value: str) -> tuple[int, int, int]:
    if type(value) is not str or not re.fullmatch(r'(0|[1-9][0-9]{0,8})\.(0|[1-9][0-9]{0,8})\.(0|[1-9][0-9]{0,8})', value):
        raise Problem('graph-conflict', 'profile supports stable three-component versions only')
    return tuple(map(int, value.split('.')))


def satisfies(actual: str, requirement: str) -> bool:
    if type(requirement) is not str or not requirement or len(requirement) > 40:
        raise Problem('graph-conflict', 'unsupported version constraint')
    operator = requirement[0] if requirement[0] in '=^~' else '^'
    wanted = version(requirement[1:] if requirement[0] in '=^~' else requirement)
    got = version(actual)
    if operator == '=':
        return got == wanted
    if operator == '~':
        upper = (wanted[0], wanted[1] + 1, 0)
    elif wanted[0] != 0:
        upper = (wanted[0] + 1, 0, 0)
    elif wanted[1] != 0:
        upper = (0, wanted[1] + 1, 0)
    else:
        upper = (0, 0, wanted[2] + 1)
    return wanted <= got < upper


def coordinate(value: str) -> str:
    value = text(value, 'package coordinate', 300)
    if ':' not in value:
        value = 'flow:' + value
    if not re.fullmatch(r'flow:[a-z][a-z0-9_.-]{0,127}/[a-z][a-z0-9_.-]{0,127}', value):
        raise Problem('graph-conflict', 'unsupported or invalid package coordinate')
    return value


def edge(value: str, exact: bool = False) -> tuple[str, str]:
    value = text(value, 'dependency', 360)
    if value.count('@') != 1:
        raise Problem('graph-conflict', 'dependency must carry a version constraint')
    base, requirement = value.split('@')
    base = coordinate(base)
    if exact and not requirement.startswith('='):
        raise Problem('graph-conflict', 'transitive dependency is not frozen: ' + base)
    satisfies('0.0.0', requirement)
    return base, requirement


def parse_lock(raw: bytes, limits: Limits = Limits()) -> dict:
    lock = closed(parse_toml(raw, limits), {'meta'}, {'package'})
    meta = closed(lock['meta'], {'schema_version', 'root_dependencies'}, {'generated_by', 'generated_at'})
    if type(meta['schema_version']) is not int or meta['schema_version'] != 7:
        raise Problem('schema', 'only VibeVM lock schema 7 is qualified for this reader')
    packages = lock.get('package', [])
    roots = meta['root_dependencies']
    if type(packages) is not list or type(roots) is not list:
        raise Problem('schema', 'package and root_dependencies must be arrays')
    if len(packages) > limits.max_packages or len(roots) > limits.max_edges:
        raise Problem('bounds', 'lock graph exceeds limits')
    by_base: dict[str, dict] = {}
    allowed = {'authors', 'dependencies', 'files_written', 'admitted_by', 'registry', 'source_ref', 'resolved_commit'}
    required = {'kind', 'name', 'group', 'version', 'source_url', 'content_hash', 'source_kind'}
    edges = 0
    for package in packages:
        closed(package, required, allowed)
        if package['kind'] != 'flow':
            raise Problem('executable-content', 'only flow packages are admitted by the data-only profile')
        base = coordinate(f"flow:{text(package['group'])}/{text(package['name'])}")
        version(package['version'])
        if base in by_base:
            raise Problem('graph-conflict', 'duplicate or ambiguous version: ' + base)
        checked_digest(package['content_hash'], tree=True)
        safe_origin(package['source_url'])
        if package.get('files_written', []) != []:
            raise Problem('executable-content', 'installer file effects are not imported')
        if type(package['source_kind']) is not str or package['source_kind'] not in {'local', 'registry', 'git'}:
            raise Problem('schema', 'unsupported package source kind')
        deps = package.get('dependencies', [])
        if type(deps) is not list:
            raise Problem('schema', 'dependencies must be an array')
        edges += len(deps)
        if edges > limits.max_edges:
            raise Problem('bounds', 'dependency count exceeds limit')
        normalized = {key: package[key] for key in required}
        normalized['id'] = base + '@' + package['version']
        for dependency in deps:
            edge(dependency, exact=True)
        normalized['dependencies'] = sorted(deps)
        for key in ('registry', 'source_ref', 'resolved_commit'):
            if key in package:
                normalized[key] = text(package[key])
        by_base[base] = normalized
    root_edges = []
    seen_roots = set()
    for value in roots:
        base, constraint = edge(value)
        if base in seen_roots or base not in by_base or not satisfies(by_base[base]['version'], constraint):
            raise Problem('graph-conflict', 'root constraint conflict: ' + base)
        seen_roots.add(base)
        root_edges.append({'coordinate': base, 'constraint': constraint})
    adjacency: dict[str, list[str]] = {}
    for base, package in by_base.items():
        children = []
        for value in package['dependencies']:
            target, constraint = edge(value, exact=True)
            if target not in by_base or not satisfies(by_base[target]['version'], constraint) or target in children:
                raise Problem('graph-conflict', base + ' -> ' + target + ': incompatible or missing dependency')
            children.append(target)
        adjacency[base] = children
    visiting: list[str] = []
    visited: set[str] = set()

    def visit(base: str) -> None:
        if base in visiting:
            raise Problem('graph-cycle', ' -> '.join(visiting[visiting.index(base):] + [base]))
        if base in visited:
            return
        visiting.append(base)
        for target in adjacency[base]:
            visit(target)
        visiting.pop()
        visited.add(base)
    for base in sorted(seen_roots):
        visit(base)
    if visited != by_base.keys():
        raise Problem('graph-conflict', 'lock contains unreachable packages')
    return {'schema_version': 7, 'roots': sorted(root_edges, key=lambda item: item['coordinate']),
            'packages': sorted(by_base.values(), key=lambda item: item['id'])}


def validate_manifest(raw: bytes, roots: list[dict] | None = None, package: dict | None = None,
                      limits: Limits = Limits()) -> dict:
    manifest = parse_toml(raw, limits)
    if any(key in manifest for key in ('lifecycle', 'hooks', 'scripts', 'build', 'mcp', 'tools', 'app', 'actions')):
        raise Problem('executable-content', 'executable manifest extensions are not admitted')
    closed(manifest, set(), {'package', 'requires', 'compatibility', 'boot_snippet'})
    requires = manifest.get('requires', {})
    closed(requires, set(), {'packages'})
    declarations = requires.get('packages', {})
    if type(declarations) is not dict:
        raise Problem('schema', 'requires.packages must be a table')
    declared = sorted([{'coordinate': coordinate(key), 'constraint': value} for key, value in declarations.items()],
                      key=lambda item: item['coordinate'])
    for declaration in declared:
        satisfies('0.0.0', declaration['constraint'])
    if roots is not None and declared != roots:
        raise Problem('graph-conflict', 'authored root dependencies and frozen lock differ')
    if 'package' in manifest or package is not None:
        metadata = closed(manifest.get('package'), {'kind', 'name', 'group', 'version', 'license'},
                          {'epoch', 'format', 'authors', 'description', 'keywords', 'homepage', 'repository'})
        text(metadata['license'], 'license')
        for key in ('homepage', 'repository'):
            if key in metadata:
                safe_origin(metadata[key])
    if package is not None:
        if any(metadata[key] != package[key] for key in ('kind', 'name', 'group', 'version')):
            raise Problem('integrity', 'package manifest identity differs from lock')
        dependencies = sorted([{'coordinate': edge(value, True)[0], 'constraint': edge(value, True)[1]}
                               for value in package['dependencies']], key=lambda item: item['coordinate'])
        actual = {item['coordinate']: item['constraint'][1:] for item in dependencies}
        if ({item['coordinate'] for item in declared} != actual.keys()
                or any(not satisfies(actual[item['coordinate']], item['constraint']) for item in declared)):
            raise Problem('graph-conflict', 'package manifest dependencies differ from frozen lock')
    if 'compatibility' in manifest:
        compatibility = closed(manifest['compatibility'], set(), {'min_vibe_version', 'requires_kinds'})
        if version(compatibility.get('min_vibe_version', '0.0.0')) > version('1.0.0'):
            raise Problem('unqualified', 'package requires a newer VibeVM format profile')
        kinds = compatibility.get('requires_kinds', [])
        if type(kinds) is not list:
            raise Problem('schema', 'required kinds must be an array')
        if any(kind != 'flow' for kind in kinds):
            raise Problem('unqualified', 'package requires an unsupported kind')
    if 'boot_snippet' in manifest:
        snippet = closed(manifest['boot_snippet'], set(), {'path', 'priority', 'format', 'when'})
        if 'path' in snippet:
            safe_path(snippet['path'], limits.max_depth)
        # The adapter never evaluates this declaration; sources are explicitly selected by its caller.
    return manifest
