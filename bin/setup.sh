#!/bin/bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

# Optional local overrides (THEME_NAME, FESS_THEMES_DIR, FESS_THEMES_REF, ...).
if [ -f ./.env ]; then
  set -a
  # shellcheck disable=SC1091
  . ./.env
  set +a
fi

THEME_NAME="${THEME_NAME:-filesearch}"
THEME_DEST=./data/fess/usr/share/fess/app/themes/${THEME_NAME}

echo "Creating directories..."
mkdir -p ./data/fess/opt/fess
mkdir -p ./data/fess/var/lib/fess
mkdir -p ./data/fess/var/log/fess
mkdir -p "${THEME_DEST}"
mkdir -p ./data/semantic
mkdir -p ./data/opensearch/usr/share/opensearch/data
mkdir -p ./data/opensearch/usr/share/opensearch/config/dictionary

# Seed the live system.properties from the tracked template on first run.
# The live file is git-ignored so Fess can rewrite it at runtime (e.g. Admin >
# General) without causing git-pull conflicts; an existing file is preserved.
# To reset to defaults, delete it and re-run this script.
SYSTEM_PROPERTIES=./data/fess/opt/fess/system.properties
if [ ! -f "${SYSTEM_PROPERTIES}" ]; then
  echo "Creating ${SYSTEM_PROPERTIES} from template (theme.default=${THEME_NAME})..."
  sed "s/^theme\.default=.*/theme.default=${THEME_NAME}/" "${SYSTEM_PROPERTIES}.template" > "${SYSTEM_PROPERTIES}"
fi
if ! grep -q "^theme.default=${THEME_NAME}\$" "${SYSTEM_PROPERTIES}"; then
  echo "WARNING: ${SYSTEM_PROPERTIES} does not set theme.default=${THEME_NAME};" >&2
  echo "         set it there (or under Admin > General) to activate the theme." >&2
fi

echo "Syncing '${THEME_NAME}' theme from fess-themes..."
# Source resolution:
#   FESS_THEMES_DIR  -> copy from a local fess-themes checkout (e.g. ../fess-workspace/repos/fess-themes)
#   otherwise        -> shallow clone FESS_THEMES_REPO @ FESS_THEMES_REF
FESS_THEMES_REPO="${FESS_THEMES_REPO:-https://github.com/codelibs/fess-themes.git}"
FESS_THEMES_REF="${FESS_THEMES_REF:-main}"

if [ -n "${FESS_THEMES_DIR:-}" ]; then
  src="${FESS_THEMES_DIR}/themes/${THEME_NAME}"
  if [ ! -f "${src}/theme.yml" ]; then
    echo "ERROR: ${src}/theme.yml not found (check FESS_THEMES_DIR and THEME_NAME)." >&2
    exit 1
  fi
else
  tmpdir="$(mktemp -d)"
  trap 'rm -rf "${tmpdir}"' EXIT
  git clone --depth 1 --branch "${FESS_THEMES_REF}" "${FESS_THEMES_REPO}" "${tmpdir}/fess-themes"
  src="${tmpdir}/fess-themes/themes/${THEME_NAME}"
  if [ ! -f "${src}/theme.yml" ]; then
    echo "ERROR: themes/${THEME_NAME}/theme.yml not found in ${FESS_THEMES_REPO}@${FESS_THEMES_REF}." >&2
    echo "       Use FESS_THEMES_DIR=/path/to/fess-themes to sync from a local checkout," >&2
    echo "       or THEME_NAME=<theme> to mount a theme that exists." >&2
    exit 1
  fi
fi
# Replace the contents in place (not the directory itself) so a running
# container keeps seeing the bind mount.
find "${THEME_DEST}" -mindepth 1 -delete
cp -R "${src}/." "${THEME_DEST}/"
echo "Theme synced to ${THEME_DEST}"

echo "Generating the sample file tree..."
bash ./bin/seed-sample.sh

# The themes and data/files only need to be readable by the container, so they
# stay owned by you and this script can refresh them without sudo.
if [ "$(uname -s)" = "Linux" ] ; then
  echo "Changing an owner for directories..."
  sudo chown -R 1001 ./data/fess/opt/fess
  sudo chown -R 1001 ./data/fess/var/lib/fess
  sudo chown -R 1001 ./data/fess/var/log/fess
  sudo chown -R 1000 ./data/opensearch/usr/share/opensearch/data
  sudo chown -R 1000 ./data/opensearch/usr/share/opensearch/config/dictionary
fi
