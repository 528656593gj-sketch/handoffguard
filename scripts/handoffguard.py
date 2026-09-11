#!/usr/bin/env python3
"""Offline delivery-package auditor using only the Python standard library."""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import re
import sys
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from typing import Iterable


FINAL_TOKEN = re.compile(
    r"(?i)(?:(?<![a-z0-9])(?:final(?:ized)?|version|ver|copy|v\d+)(?![a-z0-9])|最终版?|终版|定稿|副本|修订版?)"
)
TRAILING_VERSION = re.compile(r"(?i)(?:[\s._-]*[\[(]?\d+[\])]?)$")
JUNK_NAMES = {".ds_store", "thumbs.db", "desktop.ini"}
TEMP_SUFFIXES = {".tmp", ".temp", ".bak", ".part", ".crdownload"}


@dataclass(frozen=True)
class FileEntry:
    path: str
    size: int
    sha256: str
    detected_type: str = "unknown"


@dataclass
class Finding:
    severity: str
    code: str
    message: str
    files: list[str]


def _inspect_stream(stream) -> tuple[str, str]:
    digest = hashlib.sha256()
    head = b""
    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
        if not head:
            head = chunk[:32]
        digest.update(chunk)
    if not head:
        detected = "empty"
    elif head.startswith(b"PK\x03\x04"):
        detected = "zip-container"
    elif head.startswith(b"%PDF"):
        detected = "pdf"
    elif head.startswith(b"\x89PNG\r\n\x1a\n"):
        detected = "png"
    elif head.startswith(b"\xff\xd8\xff"):
        detected = "jpeg"
    elif len(head) >= 12 and head[4:8] == b"ftyp":
        detected = "mp4-family"
    elif b"\x00" not in head:
        detected = "text-or-unknown"
    else:
        detected = "binary"
    return digest.hexdigest(), detected


def scan_directory(root: Path) -> list[FileEntry]:
    entries: list[FileEntry] = []
    for path in sorted(p for p in root.rglob("*") if p.is_file() and not p.is_symlink()):
        with path.open("rb") as stream:
            digest, detected = _inspect_stream(stream)
        entries.append(FileEntry(path.relative_to(root).as_posix(), path.stat().st_size, digest, detected))
    return entries


def scan_zip(archive: Path) -> list[FileEntry]:
    entries: list[FileEntry] = []
    with zipfile.ZipFile(archive) as bundle:
        for info in sorted(bundle.infolist(), key=lambda item: item.filename):
            if info.is_dir():
                continue
            name = info.filename
            try:
                name = name.encode("cp437").decode("utf-8")
            except (UnicodeEncodeError, UnicodeDecodeError):
                pass
            clean = PurePosixPath(name)
            if clean.is_absolute() or ".." in clean.parts:
                raise ValueError(f"unsafe ZIP entry: {info.filename}")
            if "__MACOSX" in clean.parts or clean.name.startswith("._"):
                continue
            with bundle.open(info) as stream:
                digest, detected = _inspect_stream(stream)
            entries.append(FileEntry(clean.as_posix(), info.file_size, digest, detected))
    return entries


def load_entries(target: Path) -> list[FileEntry]:
    if target.is_dir():
        return scan_directory(target)
    if target.is_file() and target.suffix.lower() == ".zip":
        return scan_zip(target)
    raise ValueError("target must be a directory or a .zip archive")


def _normalized_final_key(path: str) -> tuple[str, str, str] | None:
    item = PurePosixPath(path)
    stem = item.stem
    if item.suffix and stem.casefold().endswith(item.suffix.casefold()):
        stem = PurePosixPath(stem).stem
    if not FINAL_TOKEN.search(stem):
        return None
    normalized = FINAL_TOKEN.sub("", stem)
    normalized = TRAILING_VERSION.sub("", normalized)
    normalized = re.sub(r"[\s._\-()\[\]]+", "", normalized).casefold()
    return (item.parent.as_posix(), normalized or "_", item.suffix.casefold())


def _matches(entry: FileEntry, rule: dict) -> bool:
    path = entry.path.casefold()
    extensions = rule.get("extensions") or []
    normalized_exts = {
        (ext if str(ext).startswith(".") else f".{ext}").casefold() for ext in extensions
    }
    if normalized_exts and PurePosixPath(path).suffix.casefold() not in normalized_exts:
        return False
    patterns = [str(pattern).casefold() for pattern in (rule.get("patterns") or [])]
    if patterns and not any(fnmatch.fnmatch(path, pattern) for pattern in patterns):
        return False
    return bool(normalized_exts or patterns)


def audit(entries: list[FileEntry], rules: dict | None = None) -> list[Finding]:
    findings: list[Finding] = []

    empty = [entry.path for entry in entries if entry.size == 0]
    if empty:
        findings.append(Finding("ERROR", "EMPTY_FILE", "Empty files found.", empty))

    hashes: dict[str, list[str]] = {}
    for entry in entries:
        if entry.size:
            hashes.setdefault(entry.sha256, []).append(entry.path)
    for paths in hashes.values():
        if len(paths) > 1:
            findings.append(Finding("WARNING", "DUPLICATE_CONTENT", "Files have identical content.", paths))

    final_groups: dict[tuple[str, str, str], list[str]] = {}
    for entry in entries:
        key = _normalized_final_key(entry.path)
        if key:
            final_groups.setdefault(key, []).append(entry.path)
    for paths in final_groups.values():
        if len(paths) > 1:
            findings.append(Finding("WARNING", "MULTIPLE_FINALS", "Multiple files look like final versions of the same deliverable.", paths))

    junk = [
        entry.path
        for entry in entries
        if PurePosixPath(entry.path).name.casefold() in JUNK_NAMES
        or PurePosixPath(entry.path).suffix.casefold() in TEMP_SUFFIXES
    ]
    if junk:
        findings.append(Finding("WARNING", "PACKAGE_JUNK", "Temporary or system files found.", junk))

    doubled_extensions = []
    for entry in entries:
        item = PurePosixPath(entry.path)
        suffix = item.suffix.casefold()
        if suffix and item.stem.casefold().endswith(suffix):
            doubled_extensions.append(entry.path)
    if doubled_extensions:
        findings.append(Finding("WARNING", "DOUBLE_EXTENSION", "A file repeats its extension and may have been renamed incorrectly.", doubled_extensions))

    expected_types = {
        ".txt": {"text-or-unknown"}, ".md": {"text-or-unknown"}, ".csv": {"text-or-unknown"},
        ".json": {"text-or-unknown"}, ".srt": {"text-or-unknown"}, ".pdf": {"pdf"},
        ".png": {"png"}, ".jpg": {"jpeg"}, ".jpeg": {"jpeg"},
        ".mp4": {"mp4-family"}, ".mov": {"mp4-family"},
        ".docx": {"zip-container"}, ".xlsx": {"zip-container"}, ".pptx": {"zip-container"},
        ".zip": {"zip-container"},
    }
    mismatches = []
    for entry in entries:
        extension = PurePosixPath(entry.path).suffix.casefold()
        expected = expected_types.get(extension)
        if entry.detected_type not in {"empty", "unknown", "binary"} and expected and entry.detected_type not in expected:
            mismatches.append(f"{entry.path} (looks like {entry.detected_type})")
    if mismatches:
        findings.append(Finding("WARNING", "EXTENSION_MISMATCH", "File contents do not match their filename extensions.", mismatches))

    if rules:
        for index, rule in enumerate(rules.get("required", []), start=1):
            label = str(rule.get("label") or f"Rule {index}")
            if not rule.get("extensions") and not rule.get("patterns"):
                findings.append(Finding("ERROR", "INVALID_RULE", f"{label}: rule needs extensions or patterns.", []))
                continue
            matches = [entry.path for entry in entries if _matches(entry, rule)]
            minimum = int(rule.get("min_count", 1))
            maximum = rule.get("max_count")
            if len(matches) < minimum:
                findings.append(Finding("ERROR", "MISSING_REQUIRED", f"{label}: expected at least {minimum}, found {len(matches)}.", matches))
            if maximum is not None and len(matches) > int(maximum):
                findings.append(Finding("WARNING", "TOO_MANY_MATCHES", f"{label}: expected at most {maximum}, found {len(matches)}.", matches))

    return findings


def render_markdown(target: Path, entries: list[FileEntry], findings: list[Finding], rules: dict | None) -> str:
    errors = sum(item.severity == "ERROR" for item in findings)
    warnings = sum(item.severity == "WARNING" for item in findings)
    project = (rules or {}).get("project_name") or target.name
    status = "PASS" if not errors else "BLOCKED"
    lines = [
        f"# HandoffGuard report: {project}",
        "",
        f"**Status:** {status}  ",
        f"**Files:** {len(entries)}  ",
        f"**Errors:** {errors}  ",
        f"**Warnings:** {warnings}",
        "",
        "## Findings",
        "",
    ]
    if not findings:
        lines.append("No issues found by the configured checks.")
    for item in findings:
        lines.extend([f"### {item.severity} · {item.code}", "", item.message])
        if item.files:
            lines.extend(["", *[f"- `{path}`" for path in item.files]])
        lines.append("")
    lines.extend(["## Manifest", "", "| File | Size (bytes) | Detected | SHA-256 |", "| --- | ---: | --- | --- |"])
    lines.extend(f"| `{entry.path}` | {entry.size} | {entry.detected_type} | `{entry.sha256[:12]}…` |" for entry in entries)
    lines.extend(["", "> Passing this audit verifies package structure, not creative or semantic correctness.", ""])
    return "\n".join(lines)


def read_rules(path: Path | None) -> dict | None:
    if path is None:
        return None
    with path.open("r", encoding="utf-8") as stream:
        data = json.load(stream)
    if not isinstance(data, dict) or not isinstance(data.get("required", []), list):
        raise ValueError("rules must be a JSON object with a 'required' array")
    return data


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Audit a delivery folder or ZIP before handoff.")
    parser.add_argument("target", type=Path, help="Directory or ZIP archive to inspect")
    parser.add_argument("--rules", type=Path, help="Optional JSON checklist")
    parser.add_argument("--output", type=Path, default=Path("handoffguard-report.md"), help="Markdown report path")
    parser.add_argument("--json-output", type=Path, help="Optional machine-readable report path")
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        rules = read_rules(args.rules)
        entries = load_entries(args.target)
        findings = audit(entries, rules)
        report = render_markdown(args.target, entries, findings, rules)
        args.output.write_text(report, encoding="utf-8")
        if args.json_output:
            payload = {"target": str(args.target), "files": [asdict(x) for x in entries], "findings": [asdict(x) for x in findings]}
            args.json_output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    except (OSError, ValueError, json.JSONDecodeError, zipfile.BadZipFile) as error:
        print(f"handoffguard: {error}", file=sys.stderr)
        return 2
    print(f"Report written to {args.output}")
    return 1 if any(item.severity == "ERROR" for item in findings) else 0


if __name__ == "__main__":
    raise SystemExit(main())
