# Homebrew distribution

Treestamp's command-line interface and terminal editor are packaged in the separate [Reponomics Homebrew tap](https://github.com/reponomics/homebrew-tap). The formula uses the published PyPI source distribution and installs the application's Python dependencies in a private environment. The hosted web editor remains independently deployed.

Published on 2026-11-05: the v1.0.0 formula passed local source installation, its functional test, style, strict online audit, livecheck, and the installed-editor journey. Clean macOS and Linux source-install CI also passed before [the formula PR](https://github.com/reponomics/homebrew-tap/pull/1) was merged. Homebrew resolves the published formula as version 1.0.0.

## Installation and ownership

Install and update it with:

```sh
brew install reponomics/tap/treestamp
brew update
brew upgrade reponomics/tap/treestamp
```

Homebrew installs Python, Git, and the Python dependencies needed by the terminal editor. The initial distribution installs from source; prebuilt bottles and automatic formula updates are not enabled.

The [tap README](https://github.com/reponomics/homebrew-tap#readme) contains the user-facing installation instructions and formula maintenance commands. The tap owns `Formula/treestamp.rb` and its GitHub workflows. This repository owns application releases, the PyPI artifact, and the public Treestamp documentation. Changes to the tap do not require republishing the application.

## Initial release record

The formula targets [Treestamp 1.0.0 on PyPI](https://pypi.org/project/treestamp/1.0.0/#files):

```text
URL: https://files.pythonhosted.org/packages/ef/9e/8fa7f2f3712bccc8a7b0820494b9309d52e2536368f82386eecf5f94aa62/treestamp-1.0.0.tar.gz
SHA-256: 753f6f4b80227bb7121b835fcdca6f8965b302fff9d0edde745d53ca368aefbb
```

The initial formula declares `git` and `python@3.15`, includes `Language::Python::Virtualenv`, and installs with `virtualenv_install_with_resources`. It packages the normal application dependencies without the `dev` extra or the hosted package. The nine checksummed Python resources resolved for this release are:

| Resource | Version |
| --- | --- |
| linkify-it-py | 2.2.0 |
| markdown-it-py | 4.2.0 |
| mdit-py-plugins | 0.6.1 |
| mdurl | 0.1.2 |
| platformdirs | 4.14.4 |
| pygments | 2.21.0 |
| rich | 15.0.0 |
| textual | 8.2.8 |
| typing-extensions | 4.16.0 |

These versions record the initial packaging decision; consult the [current formula](https://github.com/reponomics/homebrew-tap/blob/main/Formula/treestamp.rb) for subsequent changes. Homebrew resolves the published dependency ranges for its selected Python independently of `uv.lock`, which also covers this repository's development and hosted environments. The pinned Hatchling build backend is handled by Homebrew's Python build machinery and was exercised by the local source installation.

## Updating the formula

Start from an up-to-date checkout of the tap's `main` branch and create a dedicated update branch. Confirm that the intended Treestamp version has been published to PyPI before editing the formula.

1. Obtain the source archive URL and SHA-256 from that exact PyPI release. Update the formula's `url` and `sha256`; the version is inferred from the archive name.
2. Resolve the Python resources with the command below and inspect every version, URL, and checksum. Resolve all errors before proceeding.
3. Reinstall from source and run the validation commands below. Exercise the installed terminal editor as well as the headless CLI.
4. Update the tap README if installation behavior or supported platforms changed, then submit a pull request.
5. Merge after review and successful source-install CI on both runners. Confirm installation from the published tap in a clean Homebrew environment before announcing the release.

```sh
brew trust --formula reponomics/tap/treestamp
brew update-python-resources --install-dependencies reponomics/tap/treestamp
```

The initial v1.0.0 package was published on the day it was packaged. Homebrew's release cooldown rejected automatic resource resolution, so the maintainer reviewed the release and used `--ignore-main-package-cooldown`. This third-party-tap exception applies only to the main package during resource resolution; dependency cooldowns remain in force. For future releases, either wait for the cooldown or use the same targeted exception after reviewing the release:

```sh
brew update-python-resources \
  --install-dependencies \
  --ignore-main-package-cooldown \
  reponomics/tap/treestamp
```

If dependency fixes require repackaging an unchanged Treestamp version, increment the formula's `revision` so installed copies become eligible for an upgrade. Never change the published PyPI artifact in place. The tap uses manual updates; cross-repository release automation requires a separate reviewed change and appropriately scoped credentials.

## Validation and CI

From the tap checkout, validate the formula against the selected Homebrew Python:

```sh
brew style reponomics/tap/treestamp
brew reinstall --build-from-source reponomics/tap/treestamp
brew test reponomics/tap/treestamp
brew audit --strict --online reponomics/tap/treestamp
brew livecheck reponomics/tap/treestamp
```

Use `brew install --build-from-source` for a first installation. `brew livecheck` must identify the intended PyPI version. A declaration of Python 3.11 or newer does not replace testing the interpreter selected by Homebrew.

The formula's functional test checks the installed version, imports `treestamp.tui`, creates and stages a fixture Git repository, renders its tree, confirms that a stale document exits with status 1, updates the document, and confirms a clean check. An import alone does not exercise editor behavior: also run the installed-editor journey or manually open the installed terminal editor and verify navigation, annotation, hiding, and writing.

Use `scripts/installed_editor_check.py` from the exact published source release for the installed-editor journey, together with the fixture in that release's `scripts/distribution_check.py`. For v1.0.0, the driver invokes `--load README.md`; earlier drivers using `--document` and a startup loading sequence are incompatible. Run it with the Homebrew formula's `libexec/bin/python`, from a temporary fixture repository outside the source checkout, with `PYTHONPATH` unset so it tests the installed application.

The [Formula CI workflow](https://github.com/reponomics/homebrew-tap/blob/main/.github/workflows/tests.yml) tests source installation on `macos-26` and `ubuntu-24.04`. Its Homebrew setup action is pinned to a full commit SHA and checks out the tested commit. Workflow permissions are read-only; the jobs run style, source installation, the formula test, and strict online audit. Dependabot proposes action updates. Scheduled formula autobumping and bottle publication are disabled. Check both `Source install` jobs before merging.

## Recovery during initial formula creation

The tap scaffold already exists, so ordinary release updates edit the existing formula rather than recreating the tap or running `brew create` again. For a new formula setup, grant formula-specific trust before creating and loading the formula:

```sh
brew trust --formula reponomics/tap/treestamp
```

With Homebrew 7.0.12, the initial `brew create --python` invocation wrote `Formula/treestamp.rb` but failed while loading it because trust had not yet been granted. Resource resolution can also fail after the file is written and before the editor opens. If the formula file exists after an error, open and complete that file, grant formula-specific trust if required, and rerun `brew update-python-resources`. Do not rerun `brew create` against the existing file. If no file was written, resolve the reported creation error before retrying.

See [Homebrew's Python formula guidance](https://docs.brew.sh/Language-Specific-Formulae#python), [Formula Cookbook](https://docs.brew.sh/Formula-Cookbook), and [tap maintenance documentation](https://docs.brew.sh/How-to-Create-and-Maintain-a-Tap) when adapting these procedures to later Homebrew versions.
