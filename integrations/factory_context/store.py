"""Private immutable generations with an fsync/rename compare-and-swap pointer.

The caller supplies authenticated scope and current policy. A store root must be
OS-isolated from other tenants; a Python object is not an authentication boundary.
"""
from __future__ import annotations

from contextlib import contextmanager
import fcntl
import os
from pathlib import Path
import re
import stat
from typing import Iterator
import uuid

from .boundary import (Limits, Problem, _read_at, canonical, closed, decode_json,
                       directory, identifier, safe_path)
from .context import Bundle, replay, validate_policy


def _generation(value: str) -> str:
    if type(value) is not str or not re.fullmatch(r'[0-9a-f]{64}', value):
        raise Problem('path', 'invalid generation identity')
    return value


def _write_new(fd: int, name: str, raw: bytes, mode: int = 0o400) -> None:
    target = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode, dir_fd=fd)
    try:
        pending = memoryview(raw)
        while pending:
            written = os.write(target, pending)
            if written <= 0:
                raise OSError('short store write')
            pending = pending[written:]
        os.fsync(target)
    finally:
        os.close(target)


def _commit_pointer(fd: int, token: dict) -> None:
    temporary = '.current-' + uuid.uuid4().hex + '.json'
    try:
        _write_new(fd, temporary, canonical(token), 0o600)
        os.replace(temporary, 'current.json', src_dir_fd=fd, dst_dir_fd=fd)
        os.fsync(fd)
    finally:
        try:
            os.unlink(temporary, dir_fd=fd)
        except FileNotFoundError:
            pass


def _token(value: dict) -> dict:
    closed(value, {'generation', 'sequence'})
    _generation(value['generation'])
    if type(value['sequence']) is not int or value['sequence'] <= 0:
        raise Problem('schema', 'invalid generation sequence')
    return value


def _current(fd: int) -> dict | None:
    try:
        result = decode_json(_read_at(fd, 'current.json', Limits(max_file_bytes=4096)), 4096)
    except FileNotFoundError:
        return None
    return _token(result)


def _read_relative(fd: int, path: str, limits: Limits) -> bytes:
    safe_path(path, limits.max_depth)
    current = os.dup(fd)
    try:
        parts = path.split('/')
        for part in parts[:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=current)
            os.close(current)
            current = child
        return _read_at(current, parts[-1], limits)
    except FileNotFoundError as error:
        raise Problem('missing-object', 'generation file is unavailable') from error
    except OSError as error:
        raise Problem('path', 'generation read boundary refused') from error
    finally:
        os.close(current)


def _materialized(bundle: Bundle) -> dict[str, bytes]:
    value = bundle.value
    import base64
    objects = value['objects']
    manifest = value['manifest']
    return {**bundle.outputs, 'bundle.json': bundle.to_bytes(),
            'context-manifest.json': canonical(manifest),
            'vibe.lock': base64.b64decode(objects[manifest['transport']['raw_lock_digest']], validate=True),
            'vibe.toml': base64.b64decode(objects[manifest['semantic']['authored_manifest_digest']], validate=True)}


class Store:
    """A single tenant/repository's preparation store, not a running-agent switch."""

    def __init__(self, root: Path, tenant: str, repository: str, *, limits: Limits = Limits()):
        identifier(tenant)
        self.root = Path(os.path.abspath(root))
        self.tenant = tenant
        self.repository = repository
        self.limits = limits
        self._owner = canonical({'schema_version': 1, 'tenant': tenant, 'repository': repository})
        try:
            with directory(self.root.parent) as parent:
                try:
                    os.mkdir(self.root.name, 0o700, dir_fd=parent)
                    os.fsync(parent)
                except FileExistsError:
                    pass
            with self._locked(check_owner=False) as fd:
                try:
                    existing = _read_at(fd, '.owner.json', Limits(max_file_bytes=4096))
                except FileNotFoundError:
                    if set(os.listdir(fd)) != {'.lock'}:
                        raise Problem('admission', 'refusing to claim an existing nonempty store')
                    _write_new(fd, '.owner.json', self._owner)
                    existing = self._owner
                if existing != self._owner:
                    raise Problem('admission', 'store belongs to a different tenant/repository')
                try:
                    os.mkdir('generations', 0o700, dir_fd=fd)
                except FileExistsError:
                    pass
                child = os.open('generations', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                os.close(child)
                os.fsync(fd)
        except OSError as error:
            raise Problem('path', 'store initialization boundary refused') from error

    @contextmanager
    def _opened(self, check_owner: bool = True) -> Iterator[int]:
        with directory(self.root) as fd:
            info = os.fstat(fd)
            if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077:
                raise Problem('admission', 'store root must be private (0700) and owned by the service identity')
            if check_owner and _read_at(fd, '.owner.json', Limits(max_file_bytes=4096)) != self._owner:
                raise Problem('admission', 'store owner identity mismatch')
            yield fd

    @contextmanager
    def _locked(self, check_owner: bool = True) -> Iterator[int]:
        with self._opened(check_owner) as fd:
            lock = os.open('.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600, dir_fd=fd)
            try:
                info = os.fstat(lock)
                if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != os.getuid()
                        or stat.S_IMODE(info.st_mode) & 0o077):
                    raise Problem('path', 'unsafe store lock')
                fcntl.flock(lock, fcntl.LOCK_EX)
                yield fd
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)
                os.close(lock)

    def current(self) -> dict | None:
        with self._opened() as fd:
            return _current(fd)

    def _load_at(self, root_fd: int, generation: str, policy: dict, audit: bool) -> Bundle:
        _generation(generation)
        generations_fd = os.open('generations', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=root_fd)
        try:
            try:
                fd = os.open(generation, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=generations_fd)
            except FileNotFoundError as error:
                raise Problem('missing-object', 'required generation is unavailable') from error
            try:
                blob_limits = Limits(max_file_bytes=self.limits.max_total_bytes * 4)
                raw = _read_relative(fd, 'bundle.json', blob_limits)
                bundle = Bundle.from_bytes(raw, self.limits)
                if bundle.id != generation or bundle.to_bytes() != raw:
                    raise Problem('integrity', 'generation address or serialization mismatch')
                bundle = replay(bundle, policy, self.tenant, self.repository, audit=audit, limits=self.limits)
                expected = _materialized(bundle)
                if set(os.listdir(fd)) != {name.split('/')[0] for name in expected}:
                    raise Problem('integrity', 'generation contains unexpected or missing entries')
                for name, content in expected.items():
                    if _read_relative(fd, name, blob_limits) != content:
                        raise Problem('integrity', 'materialized generation does not match snapshot')
                if any(name.startswith('sources/') for name in expected):
                    source_fd = os.open('sources', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                    try:
                        if set(os.listdir(source_fd)) != {name[8:] for name in expected if name.startswith('sources/')}:
                            raise Problem('integrity', 'unexpected source materialization')
                    finally:
                        os.close(source_fd)
                return bundle
            finally:
                os.close(fd)
        finally:
            os.close(generations_fd)

    def load(self, generation: str, policy: dict, *, audit: bool = False) -> Bundle:
        with self._opened() as fd:
            return self._load_at(fd, generation, policy, audit)

    def publish(self, bundle: Bundle, policy: dict, *, expected: dict | None) -> dict:
        if expected is not None:
            expected = _token(decode_json(canonical(expected)))
        policy = decode_json(canonical(policy))
        bundle = replay(bundle, policy, self.tenant, self.repository, limits=self.limits)
        with self._locked() as fd:
            current = _current(fd)
            if current != expected:
                raise Problem('conflict', 'current generation changed; reconcile before retrying')
            generations_fd = os.open('generations', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            try:
                if bundle.id in os.listdir(generations_fd):
                    self._load_at(fd, bundle.id, policy, False)
                else:
                    staging = '.stage-' + uuid.uuid4().hex
                    os.mkdir(staging, 0o700, dir_fd=generations_fd)
                    stage_fd = os.open(staging, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=generations_fd)
                    try:
                        files = _materialized(bundle)
                        if any(name.startswith('sources/') for name in files):
                            os.mkdir('sources', 0o700, dir_fd=stage_fd)
                        for name, raw in files.items():
                            safe_path(name, self.limits.max_depth)
                            if name.startswith('sources/'):
                                source_fd = os.open('sources', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=stage_fd)
                                try:
                                    _write_new(source_fd, name[8:], raw)
                                    os.fsync(source_fd)
                                finally:
                                    os.close(source_fd)
                            else:
                                _write_new(stage_fd, name, raw)
                        os.fsync(stage_fd)
                    finally:
                        os.close(stage_fd)
                    os.rename(staging, bundle.id, src_dir_fd=generations_fd, dst_dir_fd=generations_fd)
                    os.fsync(generations_fd)
                    self._load_at(fd, bundle.id, policy, False)
                if current is not None and current['generation'] == bundle.id:
                    return current
                token = {'generation': bundle.id, 'sequence': 1 if current is None else current['sequence'] + 1}
                _commit_pointer(fd, token)
                return token
            finally:
                os.close(generations_fd)

    def rollback(self, generation: str, policy: dict, *, expected: dict) -> dict:
        validate_policy(policy, self.tenant, self.repository, self.limits)
        if generation not in policy['qualified_generations']:
            raise Problem('unqualified', 'rollback requires current external qualification of this exact generation')
        bundle = self.load(generation, policy)
        return self.publish(bundle, policy, expected=expected)
