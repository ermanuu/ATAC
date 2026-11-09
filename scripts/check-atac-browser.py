#!/usr/bin/env python3
"""Check ATAC's own home-widget request in a normal browser on the VM.

Without --output this is a standalone diagnostic. With --output (from the
repository) it collects a public snapshot for ROMABUS. It never exports
browser cookies. Optional dependency: playwright==1.64.1 and its Firefox build.
"""
import argparse
import json
from pathlib import Path
import sys
import time
from urllib.parse import urlparse


HOME = 'https://www.atac.roma.it/'
ENDPOINT = HOME + 'Service/WebService.asmx/GetPrimaryLinesData'
CODES = ('METROA', 'METROB', 'METROB1', 'METROC')


def read_widget(browser_type, profile, *, headed=False, manual=False, include_rows=False, executable=None,
                home=HOME, endpoint=ENDPOINT, timeout=45000):
    """Observe the widget's POST; never submit/solve a security challenge."""
    from playwright.sync_api import TimeoutError as BrowserTimeout

    profile = Path(profile).resolve()
    profile.mkdir(mode=0o700, parents=True, exist_ok=True)
    options = {'headless': not headed, 'locale': 'it-IT'}
    if executable:
        options['executable_path'] = executable
    with browser_type.launch_persistent_context(str(profile), **options) as context:
        page = context.new_page()
        if manual:
            page.goto(home, wait_until='domcontentloaded', timeout=timeout)
            input('Completa manualmente il CAPTCHA e premi Submit nel browser. '
                  'Quando compare la home ATAC, torna qui e premi Invio: ')
            # input() pauses Python's event loop; query the browser so a
            # navigation completed by the user is observed before checking it.
            current = urlparse(page.evaluate('location.href'))
            expected = urlparse(home)
            if (current.scheme, current.netloc) != (expected.scheme, expected.netloc):
                raise ValueError('Il browser non è tornato alla home ATAC: verifica manuale non completata.')
            # A fresh tab shares the verified browser session but cannot match
            # a response queued before the user completed the verification.
            page = context.new_page()
        try:
            with page.expect_response(
                lambda response: response.url == endpoint and response.request.method == 'POST',
                timeout=timeout,
            ) as pending:
                page.goto(home, wait_until='domcontentloaded', timeout=timeout)
            response = pending.value
        except BrowserTimeout:
            host = urlparse(page.url).hostname or 'pagina non caricata'
            raise ValueError(f'Nessuna risposta del widget entro il timeout. Dominio attuale: {host}. '
                             'Accesso automatico non verificato; può essere necessario un controllo manuale.') from None
        content_type = response.headers.get('content-type', '')
        if response.status != 200 or 'application/json' not in content_type.lower():
            raise ValueError(f'Il widget non ha restituito JSON: HTTP {response.status}. '
                             'Accesso automatico non verificato.')
        body = response.body()
        if len(body) > 4 * 1024 * 1024:
            raise ValueError('Risposta della fonte troppo grande.')
        rows = json.loads(body)
        if not isinstance(rows, list):
            raise ValueError('Formato JSON inatteso: la fonte non restituisce una lista di linee.')
        metro = [row for row in rows if isinstance(row, dict) and row.get('Code') in CODES and row.get('Type') == 1]
        lines = [{key: row.get(key) for key in ('Code', 'Type', 'IsOn', 'Status')} for row in metro]
        if not lines:
            raise ValueError('La risposta JSON non contiene le linee Metro attese.')
        result = {'http': response.status, 'type': content_type, 'lines': lines}
        if include_rows:
            result.update(rows=metro, fetchedAt=time.time())
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', required=True, type=Path, help='Cartella dedicata alla prova, distinta dal profilo Firefox già aperto.')
    parser.add_argument('--headed', action='store_true', help='Mostra il browser tramite X11; la prova predefinita funziona senza DISPLAY.')
    parser.add_argument('--manual', action='store_true', help='Con --headed, attendi Invio dopo la verifica manuale prima di leggere il widget.')
    parser.add_argument('--output', type=Path, help='Dal checkout: salva atomicamente lo snapshot pubblico per il backend.')
    args = parser.parse_args()
    if args.manual and not args.headed:
        parser.error('--manual richiede --headed e una sessione X11 attiva.')
    writer = None
    if args.output:
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        try:
            from server.metro_cache import write_snapshot
            writer = write_snapshot
        except ImportError:
            print('Per --output usa scripts/check-atac-browser.py dal checkout aggiornato di ROMABUS.', file=sys.stderr)
            return 2

    def fail(message, code):
        if writer:
            try:
                writer(args.output)
            except (OSError, ValueError):
                print('Impossibile aggiornare lo snapshot Metro; il backend ne applicherà la scadenza.', file=sys.stderr)
        print(message, file=sys.stderr)
        return code

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return fail('Dipendenza mancante: installa playwright==1.64.1 nella virtualenv della prova.', 2)
    try:
        with sync_playwright() as playwright:
            result = read_widget(playwright.firefox, args.profile, headed=args.headed, manual=args.manual,
                                 include_rows=bool(args.output))
        if writer:
            writer(args.output, result.pop('rows'), fetched_at=result.pop('fetchedAt'))
    except (EOFError, KeyboardInterrupt):
        return fail('Verifica manuale interrotta; accesso automatico non verificato.', 1)
    except ValueError as error:
        return fail(str(error), 1)
    except Exception as error:
        # Do not dump browser state, cookies or redirect query parameters.
        return fail(f'Prova del browser fallita ({type(error).__name__}). '
                    'Verifica installazione Firefox Playwright, dipendenze e disponibilità del profilo.', 2)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
