"""Local JSON CLI for a preparation store, not a coding-agent launcher."""
from __future__ import annotations
import argparse
from pathlib import Path
import sys
import time

from .boundary import Limits, Problem, canonical, decode_json, read_file
from .context import build, native_export
from .store import Store
from .telemetry import usage_event


def _json_file(path: str) -> dict:
    target = Path(path).absolute()
    return decode_json(read_file(target.parent, target.name), Limits().max_file_bytes)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=['build', 'replay', 'export', 'rollback'])
    parser.add_argument('--policy', required=True, help='trusted current admission policy, outside packages')
    parser.add_argument('--store', required=True, help='private tenant-isolated store root')
    parser.add_argument('--request')
    parser.add_argument('--workspace')
    parser.add_argument('--generation', help='exact generation, never an implicit current run switch')
    parser.add_argument('--tenant', help='authenticated caller tenant for replay/export/rollback')
    parser.add_argument('--repository', help='authenticated caller repository for replay/export/rollback')
    parser.add_argument('--expect', help='JSON file with exact previous current token; omitted means expect empty')
    parser.add_argument('--enable', action='store_true', help='explicitly opt in to preparation')
    parser.add_argument('--audit', action='store_true', help='audit only; requires independent policy permission')
    args = parser.parse_args(argv)
    started = time.monotonic()
    report = {'authority_effect': 'none', 'qualification': {'live_agent_cli': 'not_run',
               'shared_F24_F26_benchmark': 'not_run', 'production': 'not_qualified'}}
    status = 'failed'
    written = None
    try:
        if not args.enable:
            raise Problem('disabled', 'explicit --enable is required')
        policy = _json_file(args.policy)
        if args.operation == 'build':
            if not args.request or not args.workspace or args.audit:
                raise Problem('schema', 'build requires request/workspace and cannot activate audit data')
            request = _json_file(args.request)
            bundle = build(Path(args.workspace), request, policy, enabled=True)
            store = Store(Path(args.store), request['tenant'], request['target_repository'])
            expected = _json_file(args.expect) if args.expect else None
            token = store.publish(bundle, policy, expected=expected)
            report.update(generation=bundle.id, context_digest=bundle.context_digest, current=token)
            report['snapshot_serialized_bytes'] = len(bundle.to_bytes())
        else:
            if not args.generation or not args.tenant or not args.repository:
                raise Problem('schema', 'exact generation and caller scope are required')
            store = Store(Path(args.store), args.tenant, args.repository)
            if args.operation == 'rollback':
                if not args.expect or args.audit:
                    raise Problem('schema', 'rollback requires a current token and cannot use audit mode')
                token = store.rollback(args.generation, policy, expected=_json_file(args.expect))
                report.update(generation=args.generation, current=token)
            else:
                bundle = store.load(args.generation, policy, audit=args.audit)
                report.update(generation=bundle.id, context_digest=bundle.context_digest)
                if args.operation == 'export':
                    report['native'] = native_export(bundle, policy, args.tenant, args.repository, audit=args.audit)
        status = 'ok'
        report['status'] = status
    except Problem as error:
        # Contents, URLs and credential-like strings never enter the diagnostic event.
        report.update(status='blocked', error={'code': error.code})
    except OSError:
        report.update(status='blocked', error={'code': 'io'})
    report['usage'] = usage_event(args.operation, started, time.monotonic(), status, bytes_written=written)
    sys.stdout.buffer.write(canonical(report) + b'\n')
    return 0 if status == 'ok' else 2


if __name__ == '__main__':
    raise SystemExit(main())
