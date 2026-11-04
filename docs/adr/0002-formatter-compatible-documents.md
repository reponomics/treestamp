# ADR 0002: Formatter-compatible documents

- Status: Accepted and implemented
- Date: 2026-11-03
- Scope: Generated Markdown spacing, TOML configuration formatting, maintenance checks, and editor exports

## Context

Treestamp shares Markdown documents with editors, formatters, and linters. Previously, `check` rejected harmless formatting changes because the replacement region always used one exact layout. In a local comparison, Prettier added a blank line between the configuration comment and the code fence; mdformat and remark also added blank lines after the start marker and before the end marker. All preserved the tree and configuration values, but the resulting documents failed `check`. Markdownlint instead reported the long, single-line `hidden` array.

Generated output should cooperate with these tools without weakening tree or configuration validation. Users can review drafts and apply their own formatting before committing. Treestamp does not enforce that review step: headless `update` and the updating pre-commit hook remain available. Its default formatting therefore needs to be predictable, and `check` must accept supported equivalent layouts regardless of which tool produced them.

## Decision

### Blank lines

New output includes one blank line at each of three boundaries: after the start marker, between the configuration comment and the tree when configuration is present, and before the end marker. Existing documents may have zero or one blank line at each boundary independently. Maintenance and editor exports preserve those choices. An empty marker pair initialized by a write uses the new defaults.

This tolerance is deliberately narrow. Two or more blank lines at these boundaries still cause a formatting diff. It does not make arbitrary whitespace changes inside tree rows acceptable or change the separate blank line before an attribution trailer.

### TOML and line width

Accept equivalent TOML representations supported by the parser, including multiline arrays, comments, alternate quoting, and explicit default values. The existing schema, path, uniqueness, and row-registration checks still apply. The configuration must remain inside its recognized HTML comment wrapper; raw nested comment delimiters or a premature `-->` are not allowed even if they occur in otherwise valid TOML.

Preserve the original configuration text when its validated values are unchanged. When values change, regenerate the entire configuration using the default layout. This discards comments within the regenerated configuration. There is no promise of preserving comments or layout while modifying values.

Generated arrays stay inline when the complete assignment fits within 80 characters. Longer arrays use four-space indentation and pack as many complete entries as fit on each line, with trailing commas. Paths and inline records are never split, so individual entries may exceed 80 characters. The target applies to generated arrays, not to every line of a document or to input validity.

Eighty characters matches the markdownlint limit encountered in the compatibility experiment and provides a conservative baseline, not an inferred user preference. Projects may enforce a different width with their own tools. Treestamp neither stores a width setting nor tries to infer one from existing line lengths.

## Implementation

[document.py](../../src/treestamp/document.py) supplies the shared behavior:

- `_Spacing.from_interior` reads the three existing boundary choices. `render_interior` emits them, or the spaced defaults for new output.
- `_array_text` greedily packs already-encoded TOML entries at the 80-character target. `_settings_text` uses it for `hidden` and `special_paths`.
- `_config_text` compares the existing and generated payloads through `_metadata`, which uses `tomllib` and the existing validators. Hidden paths compare as sets and special registrations as row-to-path mappings; presentation order is not significant. Equivalent payloads retain their original text. Changed payloads use generated formatting.
- `prepare_content` combines these rules with the destination's line-ending convention and preserves bytes outside the managed region. `check` still compares the complete prepared bytes with the original; it is not a blanket semantic comparison of the tree. `update` publishes that same prepared result.

The [terminal editor](../../src/treestamp/editor.py) and [hosted preview](../../web/src/treestamp_web/preview.py) use the retained document baseline through `prepare_content` for exports and dirty-state detection. Copies and prints of loaded regions preserve supported spacing, configuration formatting, and LF or CRLF endings. Exported snippets omit a file-level UTF-8 BOM; writes preserve the original file's BOM. Newly created documents use default formatting and LF endings. Writing into another existing document follows that destination's formatting.

No new persisted settings or dependencies are introduced. The implementation was committed in `ed51c66` and `5c5b9a4`.

## Alternatives considered

| Option | Reason not chosen |
| --- | --- |
| Require formatter-ignore directives | Makes each user configure external tools to protect otherwise equivalent output |
| Keep exact canonical configuration bytes | Reports formatting-only drift and rewrites authored layouts |
| Emit every array entry on its own line | Makes large hidden-path lists unnecessarily tall, even inside a hidden comment |
| Infer a wrapping width from existing lines | Existing wrapping cannot reliably distinguish, for example, an 80-character preference from an 88-character preference |
| Remember inline versus wrapped formatting through value changes | Adds another formatting policy; a single conservative generation default is sufficient for now |
| Preserve arbitrary TOML comments while changing values | Requires more editing machinery; exact retention when values are unchanged is sufficient for this decision |

## Consequences and verification

Existing compact documents remain current without migration. Equivalent TOML formatting alone does not dirty a loaded draft or fail `check`. Real tree drift, invalid configuration, and formatting outside the supported tolerances remain detectable. A project with a stricter line-length rule may still need to reformat regenerated arrays, and long individual entries may require a local lint exception.

Regression tests cover all eight blank-line combinations with LF and CRLF, multiline and commented TOML, explicit defaults, array-of-tables syntax, compact wrapping at the width boundary, oversized entries, changed hidden paths and special registrations, editor save/copy, hosted restore, and stale-tree detection. Local formatter comparisons confirmed that the tested new output remains unchanged under Prettier 3.9.10, mdformat 1.0.0 with and without GFM, and remark with GFM; these checks are sample-based, not a guarantee for every formatter configuration or tree style.

See the [design](../design.md#document-format) and [CLI reference](../cli-reference.md#check-and-update) for the current operating contract.
