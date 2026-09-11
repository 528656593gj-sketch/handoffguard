---
name: handoffguard
description: Audit a delivery folder or ZIP before handoff. Use when a user wants to check required files, empty files, duplicates, confusing final versions, package hygiene, or produce a delivery manifest. Do not use for judging the creative quality of file contents.
---

# HandoffGuard

Inspect a delivery package deterministically before making interpretive recommendations.

## Run the audit

Use the bundled script for folders and ZIP archives:

```bash
python3 scripts/handoffguard.py <folder-or-zip> --rules <checklist.json> --output <report.md>
```

If the user has no checklist, run without `--rules` to check empty files, duplicates, confusing final versions, temporary files, and package inventory. Never invent mandatory deliverables.

When a checklist is needed, read [references/checklist-schema.md](references/checklist-schema.md). Translate the user's explicit requirements into that schema. Mark ambiguous natural-language requirements for confirmation instead of guessing.

## Interpret the result

- Separate deterministic findings from suggestions.
- Treat a missing required group, an empty file, or an unreadable package as an error.
- Treat duplicates, multiple likely final versions, and temporary/system files as warnings requiring human review.
- Do not claim that a file's content is correct merely because its name, size, and extension pass.
- Do not delete, rename, or modify inspected files unless the user explicitly asks.
- Avoid uploading confidential delivery contents to external services. The bundled audit runs locally and does not require an API key.

Summarize the most important blockers first and link or identify the generated report.

## Repair safely

When the user explicitly asks for repair, create a new ZIP and keep the original unchanged:

```bash
python3 scripts/repair_package.py <source.zip> --output <repaired.zip> --log <repair-log.md>
```

The repair removes package metadata and temporary files, removes byte-identical duplicates, repairs legacy ZIP filename encoding, fixes repeated extensions, and corrects recognizable Office document extensions. Re-run the audit on the repaired copy. Never fabricate missing subtitles, covers, documents, or other creative deliverables.
