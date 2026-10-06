"""Opt-in, data-only VibeVM context preparation. No agent or execution grants."""
from .boundary import Limits, Problem, decode_json, parse_lock, read_tree, tree_hash
from .boot import boot_block_digest, reconcile_boot
from .context import Bundle, build, native_export, replay
from .store import Store
from .telemetry import summarize_usage, usage_event

__all__ = ['Limits', 'Problem', 'Bundle', 'Store', 'build', 'replay', 'native_export',
           'decode_json', 'parse_lock', 'read_tree', 'tree_hash', 'boot_block_digest',
           'reconcile_boot', 'usage_event', 'summarize_usage']
