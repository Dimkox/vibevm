"""Lifecycle facts for the existing factory ledger; no evaluator or price guesses."""
from __future__ import annotations
import math
import uuid
from .boundary import Problem

CLOCK_DOMAIN = 'process-' + uuid.uuid4().hex

OPERATIONS = frozenset({'build', 'replay', 'publish', 'rollback', 'export', 'bootstrap'})


def usage_event(operation: str, started: float, finished: float, status: str,
                *, bytes_read: int | None = None, bytes_written: int | None = None,
                clock_domain: str = CLOCK_DOMAIN) -> dict:
    if type(clock_domain) is not str or not clock_domain or len(clock_domain) > 128:
        raise Problem('schema', 'explicit bounded monotonic clock domain is required')
    if operation not in OPERATIONS or status not in {'ok', 'failed'}:
        raise Problem('schema', 'invalid lifecycle event')
    if (type(started) not in (float, int) or type(finished) not in (float, int)
            or not math.isfinite(started) or not math.isfinite(finished) or finished < started):
        raise Problem('schema', 'invalid monotonic interval')
    for amount in (bytes_read, bytes_written):
        if amount is not None and (type(amount) is not int or amount < 0):
            raise Problem('schema', 'invalid lifecycle byte count')
    return {'schema_version': 1, 'clock_domain': clock_domain, 'operation': operation, 'status': status,
            'started_monotonic': started, 'finished_monotonic': finished,
            'wall_seconds': finished - started, 'bytes_read': bytes_read, 'bytes_written': bytes_written,
            'input_tokens': None, 'output_tokens': None, 'provider_cached_tokens': None,
            'provider_cost': None, 'currency': None, 'package_cache': 'not_measured',
            'provider_cache': 'not_measured', 'authority_effect': 'none'}


def summarize_usage(events: list[dict]) -> dict:
    """Union overlapping intervals in one clock domain; include unsuccessful attempts."""
    intervals = []
    failures = 0
    domains = set()
    for event in events:
        checked = usage_event(event['operation'], event['started_monotonic'], event['finished_monotonic'],
                              event['status'], clock_domain=event.get('clock_domain', ''))
        domains.add(checked['clock_domain'])
        if len(domains) > 1:
            raise Problem('clock-domain', 'monotonic intervals come from different clock domains')
        intervals.append((checked['started_monotonic'], checked['finished_monotonic']))
        failures += event['status'] == 'failed'
    merged = []
    for start, end in sorted(intervals):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    return {'attempts': len(events), 'failures': failures,
            'observed_wall_seconds': sum(end - start for start, end in merged),
            'input_tokens': None, 'output_tokens': None, 'provider_cost': None,
            'currency': None, 'cost_status': 'unknown', 'clock_domain': next(iter(domains), None)}
