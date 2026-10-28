# Verifying releases

Each wheel and source distribution on [PyPI](https://pypi.org/project/treestamp/) is published by this repository's `publish.yml` workflow through Trusted Publishing, with a [PEP 740](https://peps.python.org/pep-0740/) attestation. The attestation is a Sigstore signature over the file's SHA-256 digest, issued to that workflow's GitHub Actions identity. GitHub Releases have no uploaded assets.

## Verify a file

Download the release, then verify each file with [pypi-attestations](https://github.com/pypi/pypi-attestations). `pipx run pypi-attestations` works in place of `uvx pypi-attestations`.

```bash
python -m pip download --no-deps --only-binary :all: treestamp==0.1.2 -d dist
uvx pypi-attestations verify pypi --repository https://github.com/reponomics/treestamp dist/treestamp-0.1.2-py3-none-any.whl
```

A verified file prints:

```text
OK: treestamp-0.1.2-py3-none-any.whl
```

To verify a file on PyPI without downloading it first, pass its name with a `pypi:` prefix, such as `pypi:treestamp-0.1.2.tar.gz`. A file whose contents differ from the signed digest fails with `subject does not match distribution digest`; a file signed by another repository fails with `provenance was signed by repository "...", expected "reponomics/treestamp"`. Do not install a file that fails verification.

## Expected publisher identity

The signing certificate of every release file identifies this publisher:

| Field | Expected value |
| --- | --- |
| OIDC issuer | `https://token.actions.githubusercontent.com` |
| Repository | `https://github.com/reponomics/treestamp` |
| Signing workflow | `https://github.com/reponomics/treestamp/.github/workflows/publish.yml@refs/tags/vVERSION` |
| Source ref | `refs/tags/vVERSION`, the release's version tag |

`pypi-attestations verify pypi` checks the signature, the file's digest, and the publishing repository. To check the workflow and environment, read the publisher that PyPI recorded for the file:

```bash
curl -s https://pypi.org/integrity/treestamp/0.1.2/treestamp-0.1.2-py3-none-any.whl/provenance | python -m json.tool
```

Each attestation bundle's `publisher` must be `{"environment": "pypi", "kind": "GitHub", "repository": "reponomics/treestamp", "workflow": "publish.yml"}`. PyPI's page for each file shows the same details under **Provenance**.
