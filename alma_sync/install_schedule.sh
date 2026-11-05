#!/bin/bash
# Installs the Alma sync as an hourly launchd job for the current user.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON3="$(command -v python3)"
PLIST_DEST="$HOME/Library/LaunchAgents/com.alma.sync.plist"

mkdir -p "$HOME/.alma_sync"

sed -e "s#__PYTHON3__#${PYTHON3}#g" \
    -e "s#__SCRIPT_DIR__#${SCRIPT_DIR}#g" \
    -e "s#__HOME__#${HOME}#g" \
    "$SCRIPT_DIR/com.alma.sync.plist.template" > "$PLIST_DEST"

launchctl unload "$PLIST_DEST" 2>/dev/null || true
launchctl load "$PLIST_DEST"

echo "Installed and loaded: $PLIST_DEST"
echo "It will run now (RunAtLoad) and then every hour."
echo "Logs: $HOME/.alma_sync/sync.log and $HOME/.alma_sync/launchd.err.log"
echo ""
echo "To uninstall: launchctl unload $PLIST_DEST && rm $PLIST_DEST"
