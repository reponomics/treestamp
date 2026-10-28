# Changelog

## Unreleased

### Bug Fixes

- Limit documents to 100 displayed entries whose names contain the annotation delimiter (`  # `), bounding the number of special-path registrations considered during parsing. Loading or rendering a document above this limit now fails explicitly; use fewer displayed special names or a smaller subtree.

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
