# Changelog

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
