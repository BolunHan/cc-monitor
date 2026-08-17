#!/usr/bin/env bash
# Install the dsh-cc-monitor plugin into a DSH profile.
#
# Usage:
#   scripts/install-dsh-plugin.sh [package-or-tarball]
#
# With no argument it downloads the latest GitHub release tarball. Pass a
# local .tgz path or a URL to install a specific build.
set -euo pipefail

PROFILE="${DSH_PROFILE:-web}"
PKG_NAME="dsh-cc-monitor"
PKG_SPEC="${1:-https://github.com/BolunHan/cc-monitor/releases/latest/download/dsh-cc-monitor.tgz}"

echo "==> Installing ${PKG_NAME} into DSH profile '${PROFILE}'"
echo "    package: ${PKG_SPEC}"
dsh plugin --profile "${PROFILE}" add "${PKG_SPEC}"

PROFILE_DIR="${DSH_HOME:-$HOME/.dsh}/profiles/${PROFILE}"
PKG_JSON="${PROFILE_DIR}/package.json"
if [ ! -f "${PKG_JSON}" ]; then
  echo "ERROR: ${PKG_JSON} not found after install" >&2
  exit 1
fi

echo "==> Registering ${PKG_NAME} in dsh.profile.bundles"
python3 - "${PKG_JSON}" "${PKG_NAME}" <<'PY'
import json, sys
path, pkg = sys.argv[1], sys.argv[2]
with open(path) as f:
    data = json.load(f)
bundles = data.setdefault('dsh', {}).setdefault('profile', {}).setdefault('bundles', [])
if pkg not in bundles:
    bundles.append(pkg)
    with open(path, 'w') as f:
        json.dump(data, f, indent=2)
        f.write('\n')
    print(f'    added {pkg} to bundles')
else:
    print(f'    {pkg} already in bundles')
PY

echo "==> Verifying composition"
if dsh --profile "${PROFILE}" --dump-config 2>/dev/null | grep -q "name: ${PKG_NAME}"; then
  echo "OK: ${PKG_NAME} is active in profile '${PROFILE}'"
else
  echo "WARNING: ${PKG_NAME} was not found in 'dsh --profile ${PROFILE} --dump-config'" >&2
  exit 1
fi
