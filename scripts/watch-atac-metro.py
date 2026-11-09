#!/usr/bin/env python3
"""Keep one Firefox session open and observe ATAC's own widget refreshes."""
import argparse
import json
import os
from pathlib import Path
import socket
import sys
import time
from urllib.parse import urljoin, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from server.metro_cache import MAX_SIZE, SOURCE, write_snapshot

ENDPOINT = SOURCE + 'Service/WebService.asmx/GetPrimaryLinesData'
CODES = ('METROA', 'METROB', 'METROB1', 'METROC')
VERIFY_HOST = 'validate.perfdrive.com'


class ManualCheck(Exception):
    pass


class TemporaryResponse(Exception):
    pass


def notify(message):
    address = os.environ.get('NOTIFY_SOCKET')
    if address:
        if address.startswith('@'):
            address = '\0' + address[1:]
        with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as connection:
            connection.settimeout(1)
            connection.sendto(message.encode(), address)


def unavailable(output):
    try:
        write_snapshot(output)
    except (OSError, ValueError):
        print('Snapshot non aggiornabile; resta applicata la scadenza dei dati.', flush=True)


def watch_widget(browser, profile, output, *, executable=None, home=SOURCE,
                 endpoint=ENDPOINT, startup_timeout=60000, update_timeout=180000, limit=None):
    from playwright.sync_api import TimeoutError as BrowserTimeout
    profile = Path(profile).resolve()
    profile.mkdir(mode=0o700, parents=True, exist_ok=True)
    options = {'headless': True, 'locale': 'it-IT'}
    if executable:
        options['executable_path'] = executable
    with browser.launch_persistent_context(str(profile), **options) as context:
        page = context.pages[0] if context.pages else context.new_page()
        first, samples = True, 0
        try:
            while limit is None or samples < limit:
                try:
                    with page.expect_response(
                        lambda response: response.url == endpoint and response.request.method == 'POST',
                        timeout=startup_timeout if first else update_timeout,
                    ) as pending:
                        if first:
                            page.goto(home, wait_until='commit', timeout=min(startup_timeout, 45000))
                    response = pending.value
                    first = False
                except BrowserTimeout:
                    host = urlparse(page.url).hostname or ''
                    if host == VERIFY_HOST:
                        raise ManualCheck('ATAC richiede una nuova verifica manuale.') from None
                    raise TemporaryResponse('Nessun aggiornamento del widget entro il timeout.') from None
                fetched = time.time()
                redirect = urlparse(urljoin(endpoint, response.headers.get('location', ''))).hostname
                if 300 <= response.status < 400 and redirect == VERIFY_HOST:
                    raise ManualCheck('ATAC richiede una nuova verifica manuale.')
                if response.status != 200:
                    unavailable(output)
                    if samples == 0:
                        raise TemporaryResponse(f'Widget HTTP {response.status}.')
                    print(f'Widget HTTP {response.status}; attendo il prossimo aggiornamento.', flush=True)
                    notify('WATCHDOG=1\nSTATUS=Fonte Metro temporaneamente non verificabile')
                    continue
                if 'application/json' not in response.headers.get('content-type', '').lower():
                    raise ManualCheck('Il widget non restituisce JSON: serve un controllo manuale.')
                body = response.body()
                if len(body) > MAX_SIZE:
                    raise ManualCheck('Risposta troppo grande: serve un controllo della fonte.')
                try:
                    rows = json.loads(body)
                except ValueError:
                    raise ManualCheck('JSON non riconosciuto: serve un controllo della fonte.') from None
                if not isinstance(rows, list):
                    raise ManualCheck('Formato delle linee non riconosciuto.')
                metro = [row for row in rows if isinstance(row, dict) and row.get('Code') in CODES
                         and str(row.get('Type')) == '1']
                if not metro:
                    raise ManualCheck('Linee Metro assenti dalla risposta.')
                write_snapshot(output, metro, fetched_at=fetched)
                samples += 1
                notify(('READY=1\n' if samples == 1 else '') + 'WATCHDOG=1\nSTATUS=Stato Metro verificato')
                print(f'Metro: lettura verificata #{samples}.', flush=True)
            return samples
        except Exception:
            unavailable(output)
            raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as playwright:
            watch_widget(playwright.firefox, args.profile, args.output)
    except KeyboardInterrupt:
        return 0
    except ManualCheck as error:
        unavailable(args.output)
        print(str(error), file=sys.stderr, flush=True)
        return 3
    except TemporaryResponse as error:
        unavailable(args.output)
        print(str(error), file=sys.stderr, flush=True)
        return 2
    except Exception as error:
        unavailable(args.output)
        print(f'Lettore Metro interrotto ({type(error).__name__}); dati non verificabili.', file=sys.stderr, flush=True)
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
