#!/usr/bin/env bash
# Install the exact Node.js 22 runtime used for AyahOS Linux verification.
# Official release archive; SHA-256 pinned from nodejs.org SHASUMS256.txt.
# No sudo, package-manager changes, profile edits, or production side effects.
set -euo pipefail

readonly VERSION="22.23.4"
readonly ARCHIVE="node-v${VERSION}-linux-x64.tar.xz"
readonly SHA256="1805bcd35e6815559bd2eb97db438d3fdb0eb3a5e6a977b7c1badca76337e9ce"
readonly SOURCE_URL="https://nodejs.org/dist/v${VERSION}/${ARCHIVE}"

die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

[[ $# -eq 1 ]] || die "Usage: $0 --check | --install"
case "$1" in
  --check|--install) readonly MODE="$1" ;;
  *) die "Usage: $0 --check | --install" ;;
esac

[[ "$(id -u)" != "0" ]] || die "Do not run as root; use a non-root Ubuntu account."
[[ "$(uname -s)" == "Linux" && "$(uname -m)" == "x86_64" ]] ||
  die "Only Linux x86_64 is supported by this pinned artifact."
[[ -n "${HOME:-}" && "$HOME" != "/" ]] || die "Refusing unsafe HOME."

readonly OPT_DIR="${HOME}/.local/opt"
readonly BIN_DIR="${HOME}/.local/bin"
readonly INSTALL_DIR="${OPT_DIR}/node-v${VERSION}-linux-x64"

for executable in node npm npx corepack; do
  dest="${BIN_DIR}/${executable}"
  source="${INSTALL_DIR}/bin/${executable}"
  # A conflicting symlink is just as unsafe to replace as an existing file.
  if [[ -e "$dest" || -L "$dest" ]]; then
    [[ -L "$dest" && "$(readlink "$dest")" == "$source" ]] ||
      die "Existing ${dest} does not point at the pinned installation; refusing to overwrite."
  fi
done

check_installed() {
  [[ -x "${INSTALL_DIR}/bin/node" ]] ||
    die "Node v${VERSION} not installed under ${INSTALL_DIR}."
  actual_version="$("${INSTALL_DIR}/bin/node" --version)" ||
    die "Unable to execute pinned Node."
  [[ "$actual_version" == "v${VERSION}" ]] ||
    die "Wrong Node version: ${actual_version}; expected v${VERSION}."
  for executable in node npm npx corepack; do
    [[ -e "${INSTALL_DIR}/bin/${executable}" ]] ||
      die "Missing ${executable} in pinned Node installation."
    [[ -L "${BIN_DIR}/${executable}" ]] ||
      die "Missing local ${executable} symlink."
    [[ "$(readlink "${BIN_DIR}/${executable}")" == "${INSTALL_DIR}/bin/${executable}" ]] ||
      die "Unexpected ${executable} symlink target."
  done
  printf 'PASS: Linux x86_64 Node %s at %s\n' "$actual_version" "$INSTALL_DIR"
}

if [[ "$MODE" == "--check" ]]; then
  check_installed
  exit 0
fi

for executable in curl tar sha256sum mktemp; do
  command -v "$executable" >/dev/null ||
    die "Missing required tool: ${executable}"
done

mkdir -p "$OPT_DIR" "$BIN_DIR"

if [[ ! -e "${INSTALL_DIR}/bin/node" ]]; then
  [[ ! -e "$INSTALL_DIR" && ! -L "$INSTALL_DIR" ]] ||
    die "Partial installation at ${INSTALL_DIR}; refusing to overwrite."
  tmpdir="$(mktemp -d "${OPT_DIR}/.node-download.XXXXXXXX")"
  trap 'rm -rf -- "$tmpdir"' EXIT

  curl --fail --location --silent --show-error --retry 2 \
    --connect-timeout 10 --max-time 180 \
    --output "${tmpdir}/${ARCHIVE}" "$SOURCE_URL"
  (
    cd "$tmpdir"
    printf '%s  %s\n' "$SHA256" "$ARCHIVE" | sha256sum --check --status
  ) || die "Node archive checksum mismatch."
  tar -xJf "${tmpdir}/${ARCHIVE}" -C "$tmpdir" ||
    die "Unable to unpack verified official Node archive."
  [[ -x "${tmpdir}/node-v${VERSION}-linux-x64/bin/node" ]] ||
    die "Verified archive missing Node binary."
  mv -- "${tmpdir}/node-v${VERSION}-linux-x64" "$INSTALL_DIR"
fi

# The link targets were checked above before making any changes.
for executable in node npm npx corepack; do
  if [[ ! -L "${BIN_DIR}/${executable}" ]]; then
    ln -s -- "${INSTALL_DIR}/bin/${executable}" "${BIN_DIR}/${executable}"
  fi
done

check_installed
printf 'Use PATH="%s:$PATH" in the current shell if node is not yet found.\n' "$BIN_DIR"
