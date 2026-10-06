#!/usr/bin/env python3
"""Check cargo fmt --all roots in bounded native Windows rustfmt invocations.

Discovery follows rustfmt's cargo-fmt get_targets_recursive: all packages from
--no-deps metadata, then external local path-dependency workspaces recursively.
Source: https://github.com/rust-lang/rustfmt/blob/main/src/cargo-fmt/main.rs
"""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


# Leave ample room below CreateProcessW's 32767 UTF-16-unit command-line limit.
COMMAND_LINE_LIMIT = 20000


def cargo_metadata(manifest=None):
    command = [os.environ.get("CARGO", "cargo"), "metadata", "--no-deps", "--format-version", "1"]
    if manifest is not None:
        command.extend(["--manifest-path", str(manifest)])
    result = subprocess.run(command + ["--offline"], capture_output=True)
    if result.returncode:
        result = subprocess.run(command, capture_output=True)
    if result.returncode:
        raise RuntimeError(result.stderr.decode("utf-8", errors="replace"))
    return json.loads(result.stdout)


def canonical_target(path):
    try:
        resolved = str(Path(path).resolve(strict=True))
    except OSError:
        return path
    # Match Rust fs::canonicalize's extended physical spelling on Windows.
    if os.name == "nt" and not resolved.startswith("\\\\?\\"):
        if resolved.startswith("\\\\"):
            return "\\\\?\\UNC\\" + resolved[2:]
        return "\\\\?\\" + resolved
    return resolved


def collect_targets(manifest=None, targets=None, visited=None):
    if targets is None:
        targets = {}
    if visited is None:
        visited = set()
    metadata = cargo_metadata(manifest)
    packages = metadata["packages"]
    manifests = {os.path.normpath(package["manifest_path"]) for package in packages}
    for package in packages:
        for target in package["targets"]:
            path = canonical_target(target["src_path"])
            targets.setdefault(path, target["edition"])
        for dependency in package["dependencies"]:
            dependency_path = dependency.get("path")
            name = dependency["name"]
            if dependency_path is None or name in visited:
                continue
            dependency_manifest = Path(dependency_path) / "Cargo.toml"
            if dependency_manifest.exists() and os.path.normpath(str(dependency_manifest)) not in manifests:
                visited.add(name)
                collect_targets(dependency_manifest, targets, visited)
    if not targets:
        raise RuntimeError("Failed to find targets")
    return targets


def rustfmt_executable():
    override = os.environ.get("RUSTFMT")
    if override is not None:
        return override
    cargo_fmt = shutil.which("cargo-fmt")
    if cargo_fmt is None:
        raise RuntimeError("cargo-fmt was not found on PATH; install the repository rustfmt component")
    suffix = ".exe" if os.name == "nt" else ""
    return str(Path(cargo_fmt).with_name("rustfmt" + suffix))


def command_line_units(command):
    return len(subprocess.list2cmdline(command).encode("utf-16-le")) // 2 + 1


def commands(targets, executable):
    editions = {}
    for path, edition in sorted(targets.items()):
        editions.setdefault(edition, []).append(path)
    for edition, paths in sorted(editions.items()):
        tail = ["--edition", edition, "--check"]
        batch = []
        for path in paths:
            candidate = [executable, *batch, path, *tail]
            if command_line_units(candidate) > COMMAND_LINE_LIMIT:
                if batch:
                    yield [executable, *batch, *tail]
                    batch = []
                if command_line_units([executable, path, *tail]) > COMMAND_LINE_LIMIT:
                    raise RuntimeError(f"One rustfmt target exceeds the command-line bound: {path}")
            batch.append(path)
        if batch:
            yield [executable, *batch, *tail]


def main():
    targets = collect_targets()
    if sys.argv[1:] == ["--list-targets"]:
        print(json.dumps(targets, sort_keys=True))
        return 0
    if sys.argv[1:]:
        raise RuntimeError("usage: self-check-format-windows.py [--list-targets]")
    status = 0
    for command in commands(targets, rustfmt_executable()):
        result = subprocess.run(command)
        if result.returncode and status == 0:
            status = result.returncode
    return status


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, RuntimeError) as error:
        print(f"self-check formatter: {error}", file=sys.stderr)
        sys.exit(1)
