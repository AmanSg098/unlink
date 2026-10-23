# Jurisdiction rulesets

Rulesets are versioned YAML files: `rules/<jurisdiction>/<version>.yaml`. They're loaded into each
organisation's database by `uv run python -m app.cli load-rules` (and by `seed`). A plan records the ruleset
version it used, so old plans always show the rules they were built on.

## Rule fields

| Field | Meaning |
|---|---|
| `id` | Stable key, e.g. `IN-GRAT-001`. Code refers to rules by this key. |
| `title`, `category` | Description and grouping (notice, compensation, deduction, sequencing, protection, ...) |
| `applies_to` | Conditions: `employment_type`, `reason_codes` (empty = applies to everyone) |
| `value` | Parameters the code reads (numbers, lists, flags). Money is integer paise. |
| `source` | The statute or policy, with a section reference |
| `effective_date` | When the rule takes effect |
| `notes` | Caveats for the reviewing lawyer |

`verified_by` is not stored in the file. A lawyer records verification (name, date, note) per rule in the
app; until then the rule shows **Unverified: not for use with real employees**.

## Changing a ruleset

Never edit a loaded version in place. Copy it to a new version file (e.g. `2026.2.yaml`), make the change,
load it, and have it verified. The loader refuses a file whose content changed but whose version didn't.

## Production gate

With `RULESET_MODE=production`, a plan can't receive final approval while its ruleset has any unverified rule.
