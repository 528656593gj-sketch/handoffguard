# Checklist schema

The rules file is JSON and uses a top-level `required` array.

```json
{
  "project_name": "Campaign delivery",
  "required": [
    {
      "label": "Final video",
      "extensions": [".mp4"],
      "patterns": ["*final*", "*成片*"],
      "min_count": 1,
      "max_count": 1
    }
  ]
}
```

## Fields

- `project_name`: optional report label.
- `label`: required human-readable deliverable name.
- `extensions`: optional list of accepted lowercase or uppercase extensions. Leading dots are optional.
- `patterns`: optional filename glob patterns. A file matches when it satisfies the extension constraint and at least one pattern. Matching is case-insensitive and applies to the full relative path.
- `min_count`: minimum required matching files; defaults to `1`.
- `max_count`: optional maximum matching files.

If both `extensions` and `patterns` are absent, the rule is invalid. Keep separate deliverable categories in separate rules so counts remain meaningful.
