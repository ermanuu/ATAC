#!/bin/bash
set -euo pipefail

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
repo_dir=$(cd -- "$script_dir/.." && pwd)
deploy_prefix=${DESTDIR:-}
service_path=/usr/local/bin:/usr/bin:/bin

if [[ -n "$deploy_prefix" && "$deploy_prefix" != /* ]]; then
    echo "DESTDIR deve essere un percorso assoluto." >&2
    exit 1
fi

# DESTDIR stages files for validation; only a real install activates systemd.
if [[ -z "$deploy_prefix" ]]; then
    if [[ $EUID -ne 0 ]]; then
        echo "Esegui con sudo: sudo bash /opt/romabus/scripts/install-data-refresh.sh" >&2
        exit 1
    fi
    id romabus >/dev/null
    test -f /opt/romabus/package.json
    test -x /opt/romabus/.venv/bin/python
    runuser -u romabus -- env PATH="$service_path" node --version >/dev/null
    runuser -u romabus -- env PATH="$service_path" npm --version >/dev/null
    install -d -m 0755 -o romabus -g romabus /opt/romabus/server/data
    touch /opt/romabus/server/data/.import.lock
    chown romabus:romabus /opt/romabus/server/data/.import.lock
fi

install_file() {
    local source_file=$1 target=$2 mode=$3 backup temporary
    install -d -- "$(dirname -- "$target")"
    if [[ -e "$target" || -L "$target" ]]; then
        if cmp -s -- "$source_file" "$target"; then
            chmod "$mode" -- "$target"
            return
        fi
        backup=$(mktemp "${target}.backup.XXXXXXXX")
        cp -a -- "$target" "$backup"
        echo "Copia precedente conservata: $backup"
    fi
    temporary=$(mktemp "${target}.new.XXXXXXXX")
    install -m "$mode" -- "$source_file" "$temporary"
    mv -fT -- "$temporary" "$target"
}

for unit in romabus-data-import.service romabus-data-import.timer; do
    install_file "$repo_dir/deploy/systemd/$unit" "$deploy_prefix/etc/systemd/system/$unit" 0644
done
install_file "$script_dir/aggiorna-romabus" "$deploy_prefix/usr/local/bin/aggiorna-romabus" 0755

if [[ -n "$deploy_prefix" ]]; then
    echo "File preparati in $deploy_prefix; servizi non attivati."
    exit 0
fi

systemctl daemon-reload
systemctl enable --now romabus-data-import.timer
systemctl is-active --quiet romabus-data-import.timer
echo "Importazione giornaliera attiva: ogni giorno alle 04:00, fuso Europe/Rome."
echo "Script aggiornato: /usr/local/bin/aggiorna-romabus"
systemctl list-timers romabus-data-import.timer --no-pager
