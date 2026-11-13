#!/bin/bash
set -euo pipefail

if [[ -z ${DISPLAY:-} ]]; then
    echo "DISPLAY assente: riconnettiti con X11 forwarding attivo." >&2
    exit 1
fi
if [[ $EUID -ne 0 ]]; then
    echo "Esegui con sudo dalla sessione MobaXterm con X11 attivo." >&2
    exit 1
fi

repo_dir=/opt/romabus
state_dir=/var/lib/romabus-metro
auth_source=${XAUTHORITY:-$HOME/.Xauthority}
auth_target=$state_dir/Xauthority
if [[ ! -r "$auth_source" ]]; then
    echo "Autorizzazione X11 non leggibile: riconnettiti con X11 attivo." >&2
    exit 1
fi
test -x "$repo_dir/.venv/bin/python"
test -f "$repo_dir/scripts/check-atac-browser.py"
test -d "$state_dir/profile"
id romabus >/dev/null

systemctl stop romabus-metro-browser.service
if [[ "$auth_source" -ef "$auth_target" ]]; then
    chown romabus:romabus "$auth_target"
    chmod 0600 "$auth_target"
else
    install -o romabus -g romabus -m 0600 "$auth_source" "$auth_target"
fi

runuser -u romabus -- env \
    DISPLAY="$DISPLAY" XAUTHORITY="$auth_target" \
    PLAYWRIGHT_BROWSERS_PATH="$state_dir/browsers" \
    XDG_CACHE_HOME="$state_dir/cache" \
    XDG_CONFIG_HOME="$state_dir/config" \
    XDG_STATE_HOME="$state_dir/state" \
    "$repo_dir/.venv/bin/python" "$repo_dir/scripts/check-atac-browser.py" \
    --profile "$state_dir/profile" --headed --manual \
    --output "$repo_dir/server/data/metro-browser.json"

systemctl reset-failed romabus-metro-browser.service
systemctl start romabus-metro-browser.service
curl -fsS 'http://127.0.0.1:8000/api/metro?fresh=1'
