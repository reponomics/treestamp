# Homebrew tap setup plan

This plan distributes Treestamp's command-line interface and terminal editor through `reponomics/homebrew-tap`, using the published PyPI source distribution. Users will install it with `brew install reponomics/tap/treestamp`. The hosted web editor remains independently deployed.

Status: proposed setup, not an existing distribution channel. The PyPI metadata and local Homebrew commands were checked on 2026-10-28; the formula has not been built or installed. The initial release below is `0.1.2`. Recheck PyPI before implementation if a later release should be packaged.

The tap is a separate Git repository. This Treestamp worktree holds the plan and any eventual installation documentation or release integration, while `Formula/treestamp.rb` and the Homebrew workflows belong in the tap.

## Prerequisites and release source

- Homebrew and GitHub CLI are installed, and `gh auth status` confirms an account that can create repositories in `reponomics`.
- The intended tap repository is `reponomics/homebrew-tap`; its Homebrew shorthand is `reponomics/tap`. If that repository already exists, clone or tap it instead of running the creation commands below.
- Test on the Python minor version selected by Homebrew. Treestamp declares Python 3.11 or newer; that declaration alone does not establish compatibility with every newer interpreter.
- Use the normal published application dependencies, without the `dev` extra or the hosted package.

The [PyPI 0.1.2 release](https://pypi.org/project/treestamp/0.1.2/#files) has this source distribution:

```text
URL: https://files.pythonhosted.org/packages/ca/de/7b5a4476488a7e161bda280da6e36a88a3435a67fc2f07328a32095b34c9/treestamp-0.1.2.tar.gz
SHA-256: 846b301000d98bdc9ce2e33f6634bc287faf75b9fe74ab8c57d6a1f86e5c33e2
```

## 1. Create and publish the tap scaffold

```sh
brew update
brew tap-new --branch=main reponomics/tap
cd "$(brew --repository reponomics/tap)"
```

`tap-new` initializes and commits a local Git repository containing `Formula/`, a README, and generated GitHub configuration. All subsequent tap commands run in this directory, independently of the Treestamp checkout.

Review the generated workflows before publishing them:

- Pin each action to the full commit SHA of its reviewed current release, with a version comment.
- Keep top-level permissions read-only, normally `contents: read`; grant write permissions only to the jobs that need them.
- Keep tests for supported macOS and Linux environments. Do not advertise platforms that have not passed installation tests.
- Initially disable or remove the generated scheduled autobump workflow. Start with reviewed manual formula updates and enable automation only after the release path works.
- Review the generated bottle-publishing workflow before enabling or dispatching it. An initial installation from source does not require published bottles.

Update the tap README to describe its purpose and mark Treestamp as pending until the formula is merged. Commit any scaffold changes, then create the GitHub repository:

```sh
git add README.md .github
git commit -m "chore: configure Homebrew tap workflows"
gh repo create reponomics/homebrew-tap \
  --public \
  --source=. \
  --remote=origin \
  --push
git switch -c codex/add-treestamp
```

Configure the default branch and PR protections after CI has reported its check names. This bootstrap establishes `main` so the first formula can be reviewed in a pull request. See [Homebrew's tap setup documentation](https://docs.brew.sh/How-to-Create-and-Maintain-a-Tap).

## 2. Generate the formula

```sh
brew create --python \
  --tap=reponomics/tap \
  --set-name=treestamp \
  --set-license=MIT \
  "https://files.pythonhosted.org/packages/ca/de/7b5a4476488a7e161bda280da6e36a88a3435a67fc2f07328a32095b34c9/treestamp-0.1.2.tar.gz"
```

The command writes `Formula/treestamp.rb`, attempts automatic Python resource resolution, and then opens the editor. Resource resolution can fail before the editor opens, including when the newly published release is still subject to Homebrew's cooldown. If the file was already written, open that existing file in your editor and continue with the edits below and step 3's resource-resolution procedure. Do not rerun `brew create` against the existing file. If no file was written, resolve the reported creation error before retrying.

Verify the formula's source URL and checksum against the release information above, and set:

```ruby
desc "Generate and maintain directory trees for project documentation"
homepage "https://treestamp.reponomics.org"
license "MIT"
```

Keep the generated versioned Python dependency, `include Language::Python::Virtualenv`, and any generated dependency resources. Add `depends_on "git"`. Keep the installation method:

```ruby
def install
  virtualenv_install_with_resources
end
```

The helper creates the application environment under `libexec` and links the installed command into Homebrew's `bin`. The formula packages the PyPI artifact using Homebrew's Python helpers; it does not need the repository's development environment or `make install`. See [Python formula guidance](https://docs.brew.sh/Language-Specific-Formulae#python).

## 3. Resolve and review dependencies

The local Homebrew version checked for this plan is 7.0.10 and supports formula-specific trust and the resource options below. Check `brew help` if an older installation does not recognize them.

```sh
brew trust --formula reponomics/tap/treestamp
brew update-python-resources \
  --install-dependencies \
  reponomics/tap/treestamp
```

Inspect the generated `resource` blocks for Textual and its transitive runtime dependencies. Each source must have a fixed version and SHA-256 checksum. Resolve reported errors before proceeding; do not publish an incomplete resource list. Homebrew manages installation of the build backend through its Python build machinery. Confirm that the pinned Hatchling backend and dependency builds succeed in the actual source installation.

Homebrew resolves the published dependency ranges for its selected interpreter. The formula's resource set is reviewed separately from `uv.lock`, which also covers this repository's development and hosted environments.

If resource resolution specifically rejects the newly published Treestamp release because of its age, the maintainer can either wait for the cooldown or, after reviewing that release, use the third-party-tap exception:

```sh
brew update-python-resources \
  --install-dependencies \
  --ignore-main-package-cooldown \
  reponomics/tap/treestamp
```

This exception applies to the main package during resource resolution; dependency cooldowns still apply. See [Homebrew's dependency resource documentation](https://docs.brew.sh/Language-Specific-Formulae#python-dependency-and-resources).

## 4. Add a functional test

Replace the generated `test do` block with the following. It adapts [the existing distribution checks](../scripts/distribution_check.py), including the expected nonzero exit status for a stale tree. The Textual import checks that the terminal editor's runtime dependency is installed even though the CLI loads it lazily.

````ruby
test do
  assert_match "treestamp #{version}",
               shell_output("#{bin}/treestamp --version")
  system libexec/"bin/python", "-c", "import textual"

  system "git", "init", "-q"
  (testpath/"src").mkpath
  (testpath/"src/app.py").write "print('hello')\n"
  (testpath/"README.md").write <<~MARKDOWN
    # Fixture

    <!-- treestamp:start -->
    ```text
    .
    └── src/ (99 files)
    ```
    <!-- treestamp:end -->
  MARKDOWN
  system "git", "add", "."

  assert_match "src/ (1 file)",
               shell_output("#{bin}/treestamp --print")
  shell_output("#{bin}/treestamp check README.md", 1)
  system bin/"treestamp", "update", "README.md"
  system bin/"treestamp", "check", "README.md"
end
````

## 5. Validate and publish the formula

```sh
brew style reponomics/tap/treestamp
brew install --build-from-source reponomics/tap/treestamp
brew test reponomics/tap/treestamp
brew audit --strict --online reponomics/tap/treestamp
brew livecheck reponomics/tap/treestamp
```

If Treestamp is already installed through Homebrew, use `brew reinstall --build-from-source reponomics/tap/treestamp` after formula edits, then repeat the test. Resolve install, test, style, and audit failures. Confirm that `livecheck` identifies the PyPI version, adding a supported PyPI livecheck configuration if automatic detection fails. Manually launch the installed terminal editor in a fixture Git repository and verify navigation and a basic editing operation.

Update the tap README with the installation command, then submit the formula:

```sh
git add Formula/treestamp.rb README.md
git commit -m "feat: add treestamp Homebrew formula"
git push -u origin codex/add-treestamp
gh pr create --base main --title "feat: add treestamp Homebrew formula" \
  --body "Package the published Treestamp release with its Python runtime dependencies and a functional Git repository test."
```

Have the PR reviewed and confirm that source installation and tests pass on the intended macOS and Linux CI runners. For the initial source-only release, merge the reviewed formula without adding a bottle stanza. If publishing bottles instead, follow the generated Homebrew publishing workflow and supply the reviewed PR head SHA where supported; verify the resulting bottle metadata and installation before advertising bottles. See [the Formula Cookbook](https://docs.brew.sh/Formula-Cookbook) and [tap publishing instructions](https://docs.brew.sh/How-to-Create-and-Maintain-a-Tap).

After the formula reaches the tap's default branch, verify installation from another clean Homebrew environment:

```sh
brew install reponomics/tap/treestamp
treestamp --version
```

The direct install command adds the tap automatically. Follow Homebrew's formula-specific trust prompt if one is shown.

## 6. Document the available channel and maintain releases

Once the published formula is verified, update Treestamp's README with the Homebrew installation command and replace the obsolete text about waiting for the first PyPI release. Those application documentation changes belong in the Treestamp repository. Do not describe the tap as available before publication and installation have succeeded.

For each subsequent PyPI release:

1. Start a new formula-update branch from the tap's current `main`.
2. Obtain the new source archive URL and SHA-256 from that exact PyPI release and update the formula. Remove any old bottle stanza when preparing a source-only update; otherwise regenerate bottles through the publishing workflow.
3. Run `brew update-python-resources reponomics/tap/treestamp` and review the dependency changes.
4. Reinstall from source, run the formula test, style and audit checks, and verify the terminal editor. Run the supported platform CI matrix.
5. Review and merge the tap PR, or use the reviewed bottle-publication workflow when distributing bottles.

Users receive new formula versions with:

```sh
brew update
brew upgrade reponomics/tap/treestamp
```

If dependency fixes require repackaging an unchanged Treestamp version, increment the formula's `revision` so installed copies are eligible for an upgrade. Never change the published PyPI artifact in place. Future automation should prepare a reviewed tap PR only after PyPI publication succeeds; design its cross-repository credentials and workflow permissions as a separate follow-up.

## Completion criteria

- The public tap contains a reviewed formula whose source and dependencies have verified checksums.
- Source installation, the functional test, and the terminal editor work with the selected Homebrew Python on the advertised platforms.
- A clean environment can install the published formula with the documented command.
- The tap README and application README describe the verified installation channel.
- A maintainer can repeat the update procedure for a subsequent PyPI release.
