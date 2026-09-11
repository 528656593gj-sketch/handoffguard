#!/usr/bin/env python3
"""Create a cleaned copy of a delivery ZIP without changing the original."""

from __future__ import annotations

import argparse
import hashlib
import io
import re
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath


JUNK_NAMES = {".ds_store", "thumbs.db", "desktop.ini"}
TEMP_SUFFIXES = {".tmp", ".temp", ".bak", ".part", ".crdownload"}
VERSION_PENALTY = re.compile(r"(?i)(副本|copy|v[2-9]\d*|\([1-9]\d*\))")


@dataclass
class Candidate:
    source_name: str
    output_name: str
    data: bytes
    repairs: list[str]


def repair_encoding(name: str) -> str:
    try:
        return name.encode("cp437").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return name


def ooxml_extension(data: bytes) -> str | None:
    if not data.startswith(b"PK\x03\x04"):
        return None
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as inner:
            names = inner.namelist()
    except zipfile.BadZipFile:
        return None
    if any(name.startswith("word/") for name in names):
        return ".docx"
    if any(name.startswith("xl/") for name in names):
        return ".xlsx"
    if any(name.startswith("ppt/") for name in names):
        return ".pptx"
    return None


def extract_docx_text(data: bytes) -> str | None:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as inner:
            root = ET.fromstring(inner.read("word/document.xml"))
    except (KeyError, ET.ParseError, zipfile.BadZipFile):
        return None
    paragraphs = []
    for paragraph in (node for node in root.iter() if node.tag.endswith("}p")):
        text = "".join(node.text or "" for node in paragraph.iter() if node.tag.endswith("}t"))
        paragraphs.append(text)
    return "\n".join(paragraphs).strip()


def detected_extension(data: bytes) -> str | None:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if data.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if data.startswith(b"%PDF"):
        return ".pdf"
    return ooxml_extension(data)


def normalize_name(name: str, data: bytes) -> tuple[str, bytes, list[str]]:
    repaired = repair_encoding(name)
    actions: list[str] = []
    if repaired != name:
        actions.append("repaired filename encoding")
    item = PurePosixPath(repaired)
    suffix = item.suffix
    stem = item.stem
    if suffix and stem.casefold().endswith(suffix.casefold()):
        stem = PurePosixPath(stem).stem
        item = item.with_name(stem + suffix)
        actions.append("removed repeated extension")
    intended_text = re.search(r"(?i)\.(srt|txt|md|csv)\.docx$", item.name)
    if intended_text and ooxml_extension(data) == ".docx":
        extracted = extract_docx_text(data)
        intended_suffix = f".{intended_text.group(1).lower()}"
        if extracted and (intended_suffix != ".srt" or "-->" in extracted):
            item = item.with_suffix("")
            data = (extracted + "\n").encode("utf-8")
            actions.append(f"converted Word content to {intended_suffix}")
    detected = detected_extension(data)
    if detected in {".png", ".jpg"}:
        cleaned_stem = re.sub(r"(?i)(?:\.(?:png|jpe?g|gif|webp))+[\s.]*$", "", item.stem)
        if cleaned_stem != item.stem:
            item = item.with_name(cleaned_stem + item.suffix)
            actions.append("removed conflicting image extension")
    if detected and item.suffix.casefold() != detected:
        item = item.with_suffix(detected)
        actions.append(f"renamed extension to {detected}")
    return item.as_posix(), data, actions


def preference(candidate: Candidate) -> tuple[int, int, str]:
    penalty = len(VERSION_PENALTY.findall(candidate.output_name)) * 2 + len(candidate.repairs)
    return penalty, len(candidate.output_name), candidate.output_name.casefold()


def repair_zip(source: Path, output: Path) -> list[str]:
    candidates: list[Candidate] = []
    log: list[str] = []
    with zipfile.ZipFile(source) as bundle:
        for info in bundle.infolist():
            if info.is_dir():
                continue
            repaired_name = repair_encoding(info.filename)
            item = PurePosixPath(repaired_name)
            if item.is_absolute() or ".." in item.parts:
                raise ValueError(f"unsafe ZIP entry: {info.filename}")
            if "__MACOSX" in item.parts or item.name.startswith("._"):
                log.append(f"Removed metadata: `{repaired_name}`")
                continue
            if item.name.casefold() in JUNK_NAMES or item.suffix.casefold() in TEMP_SUFFIXES:
                log.append(f"Removed temporary/system file: `{repaired_name}`")
                continue
            data = bundle.read(info)
            output_name, data, repairs = normalize_name(info.filename, data)
            candidates.append(Candidate(repaired_name, output_name, data, repairs))

    by_hash: dict[str, list[Candidate]] = {}
    for candidate in candidates:
        digest = hashlib.sha256(candidate.data).hexdigest()
        by_hash.setdefault(digest, []).append(candidate)

    kept: list[Candidate] = []
    for group in by_hash.values():
        group.sort(key=preference)
        winner = group[0]
        kept.append(winner)
        for duplicate in group[1:]:
            log.append(f"Removed duplicate: `{duplicate.source_name}` (kept `{winner.output_name}`)")

    used: set[str] = set()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        for candidate in sorted(kept, key=lambda item: item.output_name.casefold()):
            name = candidate.output_name
            if name in used:
                item = PurePosixPath(name)
                counter = 2
                while True:
                    alternative = (item.parent / f"{item.stem}.conflict-{counter}{item.suffix}").as_posix()
                    if alternative not in used:
                        name = alternative
                        break
                    counter += 1
                log.append(f"Renamed collision: `{candidate.output_name}` → `{name}`")
            used.add(name)
            bundle.writestr(name, candidate.data)
            for action in candidate.repairs:
                log.append(f"Updated `{candidate.source_name}` → `{name}`: {action}")
    return log


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a safely repaired copy of a delivery ZIP.")
    parser.add_argument("source", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--log", type=Path, default=Path("handoffguard-repair-log.md"))
    args = parser.parse_args()
    if args.source.resolve() == args.output.resolve():
        parser.error("output must differ from source; the original is never overwritten")
    try:
        actions = repair_zip(args.source, args.output)
    except (OSError, ValueError, zipfile.BadZipFile) as error:
        parser.error(str(error))
    lines = ["# HandoffGuard repair log", "", f"Created: `{args.output.name}`", "", "## Changes", ""]
    lines.extend(f"- {action}" for action in actions)
    if not actions:
        lines.append("- No safe mechanical repairs were needed.")
    lines.extend(["", "> Missing creative assets are not fabricated. Re-audit the repaired copy to find remaining requirements.", ""])
    args.log.write_text("\n".join(lines), encoding="utf-8")
    print(f"Repaired copy written to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
