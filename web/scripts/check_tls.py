"""Reject eMudhra incident roots in the system, HTTPX, and pip trust stores.

Offline identities: https://emudhra.we-have-a-problem.com/roots.json
Run this inside the final image as well as in the development environment.
"""

from __future__ import annotations

import hashlib
import os
import ssl
from importlib.metadata import version
from pathlib import Path

import certifi
from pip._vendor import certifi as pip_certifi

BLOCKED_ROOTS = {
    "86a1ecba089c4a8d3bbe2734c612ba341d813e043cf9e8a862cd5c57a36bbe6b",
    "d7a7a0fb5d7e2731d771e9484ebcdef71d5f0c3e0a2948782bc83ee0ea699ef4",
    "7dd78d5f4f13459a83dff9abbba62edbaf6f2d102bf257fd712f4d9f2746ed8d",
    "f2edaaff3d9b701fb4d14c9f285f8c0bad90fc3bcc1fa07d47f4718edaba34a5",
}


def check_store(label: str, context: ssl.SSLContext) -> None:
    roots = context.get_ca_certs(binary_form=True)
    if not roots:
        raise SystemExit(f"FAIL {label}: empty trust store")
    fingerprints = {hashlib.sha256(root).hexdigest() for root in roots}
    blocked = fingerprints & BLOCKED_ROOTS
    if blocked:
        raise SystemExit(f"FAIL {label}: incident roots present: {sorted(blocked)}")
    print(f"PASS {label}: {len(roots)} roots, incident roots absent")


def system_context() -> ssl.SSLContext:
    """Eagerly load CA directory files that OpenSSL otherwise loads on demand."""
    context = ssl.create_default_context()
    paths = ssl.get_default_verify_paths()
    directories = os.environ.get(paths.openssl_capath_env, paths.openssl_capath)
    for directory in directories.split(os.pathsep):
        folder = Path(directory)
        if not directory or not folder.is_dir():
            continue
        for path in folder.iterdir():
            if not path.is_file():
                continue
            content = path.read_bytes()
            if (
                b"-----BEGIN CERTIFICATE-----" in content
                or b"-----BEGIN TRUSTED CERTIFICATE-----" in content
            ):
                context.load_verify_locations(cafile=str(path))
    return context


def main() -> None:
    for package, minimum in (("pip", (26, 2, 2)), ("certifi", (2026, 10, 19))):
        installed = version(package)
        if tuple(int(part) for part in installed.split(".")) < minimum:
            raise SystemExit(f"FAIL {package}: {installed} is below {minimum}")
        print(f"PASS {package}: {installed}")
    check_store("system defaults (including CA directories)", system_context())
    for label, path in (("certifi", certifi.where()), ("pip", pip_certifi.where())):
        check_store(label, ssl.create_default_context(cafile=path))


if __name__ == "__main__":
    main()
