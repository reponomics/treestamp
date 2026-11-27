# Changelog

## [2.0.0](https://github.com/reponomics/treestamp/compare/v1.1.0...v2.0.0) (2026-11-27)

Treestamp 2.0 adds editable SVG exports and guided note transfer in the terminal and browser editors, alongside a simpler command interface. This release changes several 1.x commands and retires Markdown-list treestamps; review the migration details before upgrading.

### ⚠ BREAKING CHANGES

* **Markdown-list treestamps are no longer supported.** Recreate them as fenced Unicode or ASCII treestamps before upgrading. There is no automatic list migration. ([#61](https://github.com/reponomics/treestamp/pull/61))
* **Use explicit `new` and `load` commands.** Replace `treestamp tui` with `treestamp`, and replace top-level `treestamp --load DOCUMENT` or `treestamp tui --load DOCUMENT` with `treestamp load DOCUMENT`. Use `treestamp new DIRECTORY` to create from a directory; use `load` for an existing document. The `export` command retains its own `--load` option. ([#59](https://github.com/reponomics/treestamp/pull/59))
* **Maintenance uses the staged Git index.** `check` and `update` no longer accept `--target` or `--compare`. Stage additions, deletions, and renames before opening or updating a treestamp. An editor session keeps its captured snapshot until reopened. The default document is now `README.md` in the current directory, rather than the repository-root README. ([#59](https://github.com/reponomics/treestamp/pull/59))
* **Updates stop rather than silently dropping unmatched notes.** `treestamp update DOCUMENT` exits without writing when annotated paths disappear or change kind. Use `treestamp load DOCUMENT` to transfer those notes, then Write, or explicitly omit unmatched notes with `treestamp update DOCUMENT --skip-notes-transfer`. Matching notes are retained; renames are not inferred. ([#59](https://github.com/reponomics/treestamp/pull/59))
* **Source selection moves out of the terminal editor.** The old New, Load, and Write new file actions (`N`, `l`, and `n`) are removed. Select the source through the CLI; `w` writes the loaded document and `e` exports a separate SVG. Fresh trees have no document write target: copy or print their Markdown into the desired document. `treestamp load DOCUMENT --print` extracts the saved treestamp without refreshing it; run `update` first when a refresh is wanted. ([#59](https://github.com/reponomics/treestamp/pull/59), [#61](https://github.com/reponomics/treestamp/pull/61))

### Features

#### Guided note transfer

* Both editors help recover annotations after repository changes, with destination selection, skip, undo, and confirmation before replacing an existing note. Transferring a directory also carries descendant notes whose complete relative paths and entry kinds match; conflicts and missing destinations remain individual decisions. Undo reverses the whole transfer, including descendants. ([#59](https://github.com/reponomics/treestamp/pull/59))
* Terminal transfers remain unsaved until Write. In the browser, Discard changes returns to the accepted state after transfer, preserving transfer decisions. Cancelling or failing to load a replacement source preserves the previously accepted work. ([#59](https://github.com/reponomics/treestamp/pull/59))

#### Editable SVG output

* Export treestamps as SVG from the CLI, terminal editor, or hosted editor, with adaptive, light, and dark themes. SVG files embed the textual treestamp and can be reopened, curated, checked, updated, and exported again as SVG or Markdown. New exports default to adaptive; loaded SVGs retain their theme unless explicitly changed. ([#61](https://github.com/reponomics/treestamp/pull/61))
* The hosted editor has separate Tree and Export views, with SVG preview, download, and source copying. Export preparation preserves the editing session. ([#61](https://github.com/reponomics/treestamp/pull/61))
* File exports protect existing artifacts: replacement requires `--replace` on the CLI or confirmation in the terminal editor, and export cannot overwrite its own loaded source. Export also refuses to silently discard unmatched notes. Add README image links yourself after saving the SVG. ([#61](https://github.com/reponomics/treestamp/pull/61))

For example, with an existing `assets` directory, export a saved Markdown treestamp using:

```sh
treestamp export --load README.md --format svg --output assets/treestamp.svg
```

Output paths are repository-relative. SVG support applies to treestamp-generated files with valid embedded metadata. Updating regenerates the drawing from that metadata, so manual edits to the SVG drawing are not retained.

#### Browser navigation and draft recovery

* Create a tree from a repository directory or load a document through the file/folder picker. Responsive controls support both desktop and narrow screens. Returning home no longer automatically reopens the editor; Resume restores the accepted draft and its URL. ([#59](https://github.com/reponomics/treestamp/pull/59))
* Draft restoration preserves the accepted editing baseline, including completed transfer decisions. Resume is temporary convenience rather than durable storage: copy or download your work to save it. The hosted editor does not write repository files or create commits. ([#59](https://github.com/reponomics/treestamp/pull/59), [#61](https://github.com/reponomics/treestamp/pull/61))

### Fixes and hardening

* Preserve literal filenames containing ` -> ` or ending in ` [gitlink]` instead of interpreting them as structural syntax. Upgrade readers before sharing newly generated special-name registrations with older installations. ([#61](https://github.com/reponomics/treestamp/pull/61))
* Escape terminal control characters in printed source and diagnostics when displaying them in a terminal, while preserving source bytes and newline conventions in redirected output. ([#59](https://github.com/reponomics/treestamp/pull/59))
* Preserve SVG source newline conventions during maintenance, avoiding spurious changes after CRLF checkout conversion. ([#61](https://github.com/reponomics/treestamp/pull/61))

### Build, CI, and dependencies

* Use the web image's uv pin consistently across local checks, CI, and the tool inventory. Pre-commit now uses the Ruff version installed from `uv.lock`, removing its separate version pin. ([#65](https://github.com/reponomics/treestamp/pull/65))
* Run browser journeys before building the Docker image, preventing Docker network changes from interrupting Chromium during the shared PR checkpoint. ([#66](https://github.com/reponomics/treestamp/pull/66))
* Update uv to 0.13.10, Ruff to 0.17.6, FastAPI to 0.165.0, certifi to 2026.11.20, and httpcore2/httpx2 to 2.16.2; refresh pinned GitHub Actions. ([#55](https://github.com/reponomics/treestamp/pull/55), [#57](https://github.com/reponomics/treestamp/pull/57), [#58](https://github.com/reponomics/treestamp/pull/58), [#62](https://github.com/reponomics/treestamp/pull/62), [#63](https://github.com/reponomics/treestamp/pull/63), [#64](https://github.com/reponomics/treestamp/pull/64))

See the [CLI reference](https://github.com/reponomics/treestamp/blob/main/docs/cli-reference.md) for command and migration details, and the [browser workflow guide](https://github.com/reponomics/treestamp/blob/main/docs/ui-flow.md) for source selection, transfer, and export behavior.

## [1.1.0](https://github.com/reponomics/treestamp/compare/v1.0.1...v1.1.0) (2026-11-14)


### Features

* **cli:** add general and command-specific help alias ([#51](https://github.com/reponomics/treestamp/issues/51)) ([e6cfd5b](https://github.com/reponomics/treestamp/commit/e6cfd5bf54fbd3136ab434d1245796a417b77016))

## [1.0.1](https://github.com/reponomics/treestamp/compare/v1.0.0...v1.0.1) (2026-11-07)


### Documentation

* add quicktour gif ([#44](https://github.com/reponomics/treestamp/issues/44)) ([4580ae7](https://github.com/reponomics/treestamp/commit/4580ae70a731138cb4103250b85ab71a19728df0))

## [1.0.0](https://github.com/reponomics/treestamp/compare/v0.6.0...v1.0.0) (2026-11-05)


### ⚠ BREAKING CHANGES

* prep v1 ([#34](https://github.com/reponomics/treestamp/issues/34))

### Features

* prep v1 ([#34](https://github.com/reponomics/treestamp/issues/34)) ([4a7c60a](https://github.com/reponomics/treestamp/commit/4a7c60ab4eba1e3f28326a082de0550aab17dcb7))

## [0.6.0](https://github.com/reponomics/treestamp/compare/v0.5.0...v0.6.0) (2026-11-05)


### Features

* improve compatibility with formatters ([#32](https://github.com/reponomics/treestamp/issues/32)) ([6654a92](https://github.com/reponomics/treestamp/commit/6654a9219b94d71f4ac4efa87c5adbd4ac6f0010))

## [0.5.0](https://github.com/reponomics/treestamp/compare/v0.4.0...v0.5.0) (2026-10-31)


### Features

* **web:** read credentials from separate files ([#30](https://github.com/reponomics/treestamp/issues/30)) ([9766c81](https://github.com/reponomics/treestamp/commit/9766c81c8b4ba3881429139a6076f68651f754a8))


### Documentation

* add badges to README ([#29](https://github.com/reponomics/treestamp/issues/29)) ([2ecd4d7](https://github.com/reponomics/treestamp/commit/2ecd4d7b4afedb3b43576f91ea96b2a357e7aa76))

## [0.4.0](https://github.com/reponomics/treestamp/compare/v0.3.1...v0.4.0) (2026-10-30)


### ⚠ BREAKING CHANGES

* refactor and simplify CLI and loading paths ([#26](https://github.com/reponomics/treestamp/issues/26))

### Features

* refactor and simplify CLI and loading paths ([#26](https://github.com/reponomics/treestamp/issues/26)) ([33d96d7](https://github.com/reponomics/treestamp/commit/33d96d759b9315f7446e1d2f2149567606aa44af))

## [0.3.1](https://github.com/reponomics/treestamp/compare/v0.3.0...v0.3.1) (2026-10-30)


### Bug Fixes

* normalize relative paths in editor ([#24](https://github.com/reponomics/treestamp/issues/24)) ([23484e2](https://github.com/reponomics/treestamp/commit/23484e25ac833f76eb188af8aae6689c1f3e7c46))

## [0.3.0](https://github.com/reponomics/treestamp/compare/v0.2.0...v0.3.0) (2026-10-29)


### Features

* add opt-in attribution trailer to both editors ([#20](https://github.com/reponomics/treestamp/issues/20)) ([9053a5e](https://github.com/reponomics/treestamp/commit/9053a5e99a897757cb33e59b168c7bc0e1003db1))


### Documentation

* pin README examples to the latest release ([#18](https://github.com/reponomics/treestamp/issues/18)) ([5694389](https://github.com/reponomics/treestamp/commit/5694389a51139b1d0b6c1e497d5dbdce071c2dc8))

## [0.2.0](https://github.com/reponomics/treestamp/compare/v0.1.2...v0.2.0) (2026-10-29)


### ⚠ BREAKING CHANGES

* Documents with path-only special_paths registrations must be regenerated; documents without special registrations remain supported.


### Bug Fixes

* Replace special-path identity backtracking with direct row-number-plus-path registrations.

* fix potential DoS threat and improve docs ([#15](https://github.com/reponomics/treestamp/issues/15)) ([f3c77eb](https://github.com/reponomics/treestamp/commit/f3c77eb03a45d22fa47c9fcd7a8fe02339587dd6))

## [0.1.2](https://github.com/reponomics/treestamp/compare/v0.1.1...v0.1.2) (2026-10-28)


### Bug Fixes

* fix potential redos ([#14](https://github.com/reponomics/treestamp/issues/14)) ([407a9d5](https://github.com/reponomics/treestamp/commit/407a9d54f0e9dc623127e42ded4579fb14b09ca4))


### Documentation

* add governance, design, and security assessment documents ([#12](https://github.com/reponomics/treestamp/issues/12)) ([4819b7b](https://github.com/reponomics/treestamp/commit/4819b7b65f94c6e5679febe7326a4554ef4609dc))

## [0.1.1](https://github.com/reponomics/treestamp/compare/v0.1.0...v0.1.1) (2026-10-24)


### Documentation

* update license link in README ([#6](https://github.com/reponomics/treestamp/issues/6)) ([b6d3c7c](https://github.com/reponomics/treestamp/commit/b6d3c7cacd4777efa8a1b60638a1c7053889b620))

## 0.1.0 (2026-10-22)


### Features

* import treestamp public source tree ([764f4e9](https://github.com/reponomics/treestamp/commit/764f4e9bd9e9630d628c86e90f4d813902a85e6e))
* prepare release and production deployment automation ([#1](https://github.com/reponomics/treestamp/issues/1)) ([25722b8](https://github.com/reponomics/treestamp/commit/25722b884e29dd8a4ff65e22c782f4e11ea98922))

## 0.1.0 (Unreleased)

- Create and curate README directory trees in the terminal or web editor.
- Preserve expanded directories, hidden paths, and single-line annotations when updating a tree.
- Check and update documents from the Git index or a locally available commit, with pre-commit hooks for automation.
- Export Unicode, ASCII, or Markdown list trees with optional child counts.
- Edit public GitHub repository snapshots in the hosted editor and copy the result into your project.
