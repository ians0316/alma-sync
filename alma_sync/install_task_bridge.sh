#!/bin/bash
# Lets the Alma+ Chrome extension hand your tasks to Alma Sync (one-time setup).
# Registers tasks_bridge.py as a Chrome "native messaging host" for the extension.
#
#   ./install_task_bridge.sh [extension-id]
#
# The extension id is shown on chrome://extensions (Developer mode on).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EXT_ID="${1:-eeeeihfgedonmdpiobfkoljglemeijja}"
HOST_NAME="com.alma.sync.tasks"
HOST_DIR="$HOME/Library/Application Support/Google/Chrome/NativeMessagingHosts"

# Same Python as the hourly job when available (it has the packages installed).
PYTHON3="/Library/Frameworks/Python.framework/Versions/3.13/bin/python3"
[ -x "$PYTHON3" ] || PYTHON3="$(command -v python3)"

WRAPPER="$SCRIPT_DIR/task_bridge_host.sh"
cat > "$WRAPPER" <<EOF
#!/bin/bash
exec "$PYTHON3" "$SCRIPT_DIR/tasks_bridge.py" "\$@"
EOF
chmod +x "$WRAPPER"

mkdir -p "$HOST_DIR"
cat > "$HOST_DIR/$HOST_NAME.json" <<EOF
{
  "name": "$HOST_NAME",
  "description": "Alma Sync task bridge for the Alma+ extension",
  "path": "$WRAPPER",
  "type": "stdio",
  "allowed_origins": ["chrome-extension://$EXT_ID/"]
}
EOF

echo "Installed. Chrome will now hand your Alma+ tasks to Alma Sync."
echo "Extension id: $EXT_ID"
echo "Log of task syncs: $HOME/.alma_sync/tasks_sync.log"
