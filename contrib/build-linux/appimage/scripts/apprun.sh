#!/bin/sh

set -e

APPDIR="$(dirname "$(readlink -e "$0")")"
. "$APPDIR"/common.sh

exec "$PYTHON" -s "${APPDIR}/usr/bin/electron-fittexxcoin" "$@"
