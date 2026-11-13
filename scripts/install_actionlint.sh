#!/bin/sh
# Called by make actionlint-install; verification must precede extraction.
set -eu

version=$1
binary=$2
gh=$3
test -n "$version" || { echo "Missing actionlint pin in .tool-versions" >&2; exit 1; }

case "$(uname -s)" in
    Darwin) os=darwin ;;
    Linux) os=linux ;;
    *) echo "actionlint installation supports macOS and Linux" >&2; exit 1 ;;
esac
case "$(uname -m)" in
    x86_64|amd64) arch=amd64 ;;
    arm64|aarch64) arch=arm64 ;;
    *) echo "actionlint installation supports x86_64 and ARM64" >&2; exit 1 ;;
esac

# Stage beside the destination so the final move stays on one filesystem.
mkdir -p "$(dirname "$binary")"
temporary=$(mktemp -d "$(dirname "$binary")/.actionlint.XXXXXX")
trap 'rm -rf "$temporary"' EXIT
trap 'exit 1' HUP INT TERM
archive="actionlint_${version}_${os}_${arch}.tar.gz"

"$gh" release download "v$version" --repo rhysd/actionlint \
    --pattern "$archive" --dir "$temporary"
"$gh" attestation verify "$temporary/$archive" --repo rhysd/actionlint \
    --source-ref "refs/tags/v$version"

# Read only the executable to stdout, without restoring archive paths or modes.
tar -xOzf "$temporary/$archive" actionlint > "$temporary/actionlint"
chmod 755 "$temporary/actionlint"
actual=$("$temporary/actionlint" -version)
actual=$(printf '%s\n' "$actual" | awk 'NR == 1 {sub(/^v/, ""); print; exit}')
if [ "$actual" != "$version" ]; then
    echo "Downloaded actionlint version $actual; expected $version" >&2
    exit 1
fi
mv -f "$temporary/actionlint" "$binary"
echo "Installed actionlint $version at $binary"
