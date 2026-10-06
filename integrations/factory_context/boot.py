"""Pure, receipt-checked reconciliation of the existing VibeVM managed block.

The caller retains responsibility for its installer lock and file-level CAS.
This function never writes AGENTS.md, changes bootstrap authority, or runs tools.
"""
from __future__ import annotations
import re
from .boundary import Problem, digest

START = b'<vibevm>'
END = b'</vibevm>'


def _span(existing: bytes) -> tuple[int, int] | None:
    markers = re.findall(br'</?vibevm(?:\s|>|$)', existing)
    if not markers:
        return None
    if len(markers) != 2 or existing.count(START) != 1 or existing.count(END) != 1:
        raise Problem('boot-conflict', 'malformed or competing VibeVM bootstrap blocks')
    start, end = existing.index(START), existing.index(END) + len(END)
    if start >= end - len(END):
        raise Problem('boot-conflict', 'reversed bootstrap markers')
    return start, end


def boot_block_digest(existing: bytes) -> str | None:
    span = _span(existing)
    return None if span is None else digest(existing[span[0]:span[1]])


def reconcile_boot(existing: bytes, inner: bytes, *, previous: str | None = None) -> bytes:
    if type(existing) is not bytes or type(inner) is not bytes or len(existing) > 4 * 1024 * 1024 or len(inner) > 65536:
        raise Problem('bounds', 'bootstrap bytes exceed supported bounds')
    if re.search(br'</?vibevm(?:\s|>|$)', inner):
        raise Problem('boot-conflict', 'managed content contains reserved markers')
    try:
        inner.decode('utf-8')
    except UnicodeError as error:
        raise Problem('encoding', 'managed content must be UTF-8') from error
    replacement = START + b'\n' + inner.rstrip(b'\n') + b'\n' + END
    span = _span(existing)
    if span is None:
        if previous is not None:
            raise Problem('boot-conflict', 'expected previous block is missing')
        separator = b'' if not existing or existing.endswith(b'\n') else b'\n'
        return existing + separator + replacement + b'\n'
    start, end = span
    if previous is None or digest(existing[start:end]) != previous:
        raise Problem('boot-conflict', 'existing block has no matching installer receipt')
    return existing[:start] + replacement + existing[end:]
