#!/bin/bash
set -euo pipefail
umask 022

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
repo_dir=$(cd -- "$script_dir/.." && pwd)
deploy_prefix=${DESTDIR:-}
profile_source=
state_dir=/var/lib/romabus-metro

if [[ ${1:-} == --profile-source && $# == 2 ]]; then
    profile_source=$2
elif [[ $# != 0 ]]; then
    echo "Uso: bash scripts/install-metro-browser.sh [--profile-source /percorso/profilo-verificato]" >&2
    exit 1
fi
if [[ -n "$deploy_prefix" && "$deploy_prefix" != /* ]]; then
    echo "DESTDIR deve essere un percorso assoluto." >&2
    exit 1
fi

if [[ -z "$deploy_prefix" ]]; then
    if [[ $EUID -ne 0 ]]; then
        echo "Esegui con sudo dalla copia aggiornata in /opt/romabus." >&2
        exit 1
    fi
    if [[ "$repo_dir" != /opt/romabus ]]; then
        echo "L'installazione reale richiede il checkout in /opt/romabus." >&2
        exit 1
    fi
    id romabus >/dev/null
    test -x /opt/romabus/.venv/bin/python
    if [[ -n "$profile_source" ]]; then
        test -d "$profile_source"
        # Firefox holds a POSIX lock while using a profile. Check without
        # changing or removing the source's lock or cookie files.
        /opt/romabus/.venv/bin/python - "$profile_source" <<'PY'
import fcntl
from pathlib import Path
import sys
lock = Path(sys.argv[1]) / '.parentlock'
if lock.exists():
    with lock.open('r+b') as handle:
        try:
            fcntl.lockf(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit('Chiudi Firefox sul profilo sorgente prima di copiarlo.')
PY
    fi
    install -d -m 0700 -o romabus -g romabus "$state_dir"
    install -d -m 0755 -o romabus -g romabus /opt/romabus/server/data
    if [[ -n "$profile_source" && ! -d "$state_dir/profile" ]]; then
        install -d -m 0700 -o romabus -g romabus "$state_dir/profile"
        cp -a -- "$profile_source/." "$state_dir/profile/"
        # Remove only copied, inactive profile locks; keep the source intact.
        rm -f -- "$state_dir/profile/lock" "$state_dir/profile/.parentlock" "$state_dir/profile/parent.lock"
    elif [[ -n "$profile_source" ]]; then
        echo "Profilo già presente in $state_dir/profile; copia esistente conservata."
    fi
    /opt/romabus/.venv/bin/python -m pip install -r /opt/romabus/server/requirements-browser.txt
    PLAYWRIGHT_BROWSERS_PATH="$state_dir/browsers" \
        /opt/romabus/.venv/bin/python -m playwright install --with-deps firefox
    chown -R romabus:romabus "$state_dir"
fi

install_file() {
    local source_file=$1 target=$2 backup temporary
    install -d -- "$(dirname -- "$target")"
    if [[ -e "$target" || -L "$target" ]]; then
        if cmp -s -- "$source_file" "$target"; then
            return
        fi
        backup=$(mktemp "${target}.backup.XXXXXXXX")
        cp -a -- "$target" "$backup"
        echo "Copia precedente conservata: $backup"
    fi
    temporary=$(mktemp "${target}.new.XXXXXXXX")
    install -m 0644 -- "$source_file" "$temporary"
    mv -fT -- "$temporary" "$target"
}

for unit in romabus-metro-browser.service; do
    install_file "$repo_dir/deploy/systemd/$unit" "$deploy_prefix/etc/systemd/system/$unit"
done
install_file "$repo_dir/deploy/systemd/romabus-metro-browser.conf" \
    "$deploy_prefix/etc/systemd/system/romabus.service.d/metro-browser.conf"

if [[ -n "$deploy_prefix" ]]; then
    echo "File preparati in $deploy_prefix; nessun servizio attivato."
else
    systemctl daemon-reload
    echo "File e dipendenze pronti. Timer Metro e riavvio del sito non eseguiti."
    echo "Ferma l'eventuale vecchio timer e verifica prima: sudo systemctl start romabus-metro-browser.service"
fi
