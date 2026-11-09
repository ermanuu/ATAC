"""Official service bulletins and RSM news, independent of bus position feeds."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from html.parser import HTMLParser
import hashlib
import json
import os
import re
import threading
import time
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET

from . import transit as t
from .metro_cache import read_snapshot, UNAVAILABLE as METRO_UNAVAILABLE

RSM = 'https://romamobilita.it'
ATAC_HOME = 'https://www.atac.roma.it/'
ATAC_METRO = ATAC_HOME + 'Service/WebService.asmx/GetPrimaryLinesData'
ATAC_FEED = 'https://www.atac.roma.it/feeds/stato-del-servizio-in-tempo-reale'
ATAC_STATUS = 'https://www.atac.roma.it/stato-del-servizio'
SOURCES = {'rsm-info': ('infomobilita', 'Infomobilità'), 'rsm-news': ('primo-piano', 'News')}
METRO_LINES = ('A', 'B', 'B1', 'C')
_workers = ThreadPoolExecutor(max_workers=3, thread_name_prefix='official-info')


class PlainText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.hidden = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style'): self.hidden += 1
        if tag in ('p', 'br', 'div', 'li', 'tr', 'h2', 'h3') and not self.hidden: self.parts.append('\n')

    def handle_endtag(self, tag):
        if tag in ('script', 'style'): self.hidden = max(0, self.hidden - 1)
        if tag in ('p', 'div', 'li', 'tr') and not self.hidden: self.parts.append('\n')

    def handle_data(self, text):
        if not self.hidden: self.parts.append(text)


def plain_text(value):
    parser = PlainText()
    parser.feed(value if isinstance(value, str) else '')
    return '\n'.join(' '.join(row.split()) for row in ''.join(parser.parts).splitlines() if row.strip()).strip()


def official_url(value, fallback=RSM):
    if isinstance(value, str):
        parsed = urlparse(unescape(value.strip()))
        if parsed.scheme == 'https' and parsed.hostname in ('romamobilita.it', 'www.romamobilita.it', 'www.atac.roma.it', 'atac.roma.it') and not parsed.username and not parsed.password:
            return parsed.geturl()
    return fallback


def timestamp(value):
    if not isinstance(value, str) or not value.strip(): return None
    try:
        date = datetime.fromisoformat(value.strip().replace('Z', '+00:00'))
    except ValueError:
        try: date = parsedate_to_datetime(value)
        except (ValueError, TypeError): return None
    return int(date.replace(tzinfo=timezone.utc).timestamp() if date.tzinfo is None else date.timestamp())


_CODE = r'(?:n(?:\d{1,3}|MA|MB1?|MC|3[DS])|\d{1,3}[A-Z]{0,3}|C[1-9]|H)'
_PREFIX = re.compile(r'\b(?:line[ae]|bus|autobus|tram)\b\s*(?:(?:di|del|trasporto|pubblico|bus|autobus|atac|tram|notturne|notturna)\s+){0,6}:?\s*', re.I)
_CODE_LIST = re.compile(rf'({_CODE})(?![\w])', re.I)
_SEPARATOR = re.compile(r'\s*(?:,|/|[-–]|\be\b|\bed\b)\s*', re.I)


def line_mentions(text):
    """Only explicit line lists; never confuse times, stop codes or 75 with 075."""
    found = set()
    for prefix in _PREFIX.finditer(text):
        position = prefix.end()
        for _ in range(100):
            code = _CODE_LIST.match(text, position)
            if not code: break
            found.add(code[1].upper())
            separator = _SEPARATOR.match(text, code.end())
            if not separator: break
            position = separator.end()
    # Service RSS publishers may use the line number alone as the title.
    first = text.split('\n', 1)[0].strip()
    if re.fullmatch(_CODE, first, re.I): found.add(first.upper())
    prefix = re.match(rf'^({_CODE})\s*[-:–]\s*', first, re.I)
    if prefix: found.add(prefix[1].upper())
    return sorted(found)


def category(title):
    text = title.lower()
    if re.search(r'ripristin|riapert|normale (?:servizio|percorso)|percorso regolare|bus regolari', text): return 'Ripristino'
    if 'scioper' in text: return 'Sciopero'
    if re.search(r'deviat|deviaz|percorso modific|cambio di percorso|chiusur', text): return 'Deviazione'
    if re.search(r'sospes|interrott|interruzion', text): return 'Interruzione'
    if re.search(r'nuov|novità|orari|fermate in più|estende', text): return 'Novità'
    return 'Informazione'


def parse_articles(rows, section):
    if not isinstance(rows, list): raise ValueError('Formato notizie non riconosciuto')
    articles = []
    for row in rows:
        if not isinstance(row, dict): continue
        title = plain_text((row.get('title') or {}).get('rendered'))
        text = plain_text((row.get('content') or {}).get('rendered'))
        published, updated = timestamp(row.get('date_gmt')), timestamp(row.get('modified_gmt'))
        if not title or not published: continue
        link = official_url(row.get('link'), RSM + '/news-eventi/')
        articles.append({'id': f'rsm-{row.get("id")}', 'title': title, 'text': text[:30000],
                         'summary': (plain_text((row.get('excerpt') or {}).get('rendered')) or text)[:360],
                         'url': link, 'publishedAt': published, 'updatedAt': updated or published,
                         'source': 'Roma Mobilità', 'section': section, 'category': category(title),
                         'lines': line_mentions(title + '\n' + text), 'live': False})
    return articles


def download(url, payload=None):
    headers = {'User-Agent': 'ROMABUS/1.0 (independent transit app)', 'Accept': 'application/json, application/rss+xml, text/xml', 'Cache-Control': 'no-cache'}
    data = None
    if payload is not None:
        data = json.dumps(payload).encode()
        headers['Content-Type'] = 'application/json'
    request = Request(url, data=data, headers=headers)
    with urlopen(request, timeout=8) as response:
        body = response.read(4 * 1024 * 1024 + 1)
    if len(body) > 4 * 1024 * 1024: raise ValueError('Risposta della fonte troppo grande')
    return body


def fetch_articles(kind):
    route, section = SOURCES[kind]
    after = (datetime.now(timezone.utc) - timedelta(days=30)).strftime('%Y-%m-%dT%H:%M:%SZ')
    query = urlencode({'per_page': 100, 'orderby': 'modified', 'order': 'desc', 'modified_after': after,
                       '_fields': 'id,date_gmt,modified_gmt,link,title,content,excerpt'})
    return parse_articles(json.loads(download(f'{RSM}/wp-json/wp/v2/{route}?{query}')), section)


def rss_entries(body):
    if b'<!DOCTYPE' in body.upper() or b'<!ENTITY' in body.upper(): raise ValueError('Formato XML non consentito')
    root = ET.fromstring(body)
    if root.tag.split('}')[-1] != 'rss': raise ValueError('Feed non riconosciuto')
    channel = root.find('channel')
    if channel is None: raise ValueError('Canale RSS assente')
    entries = []
    for node in channel.findall('item'):
        title = plain_text(node.findtext('title'))
        text = plain_text(node.findtext('description') or node.findtext('{http://purl.org/rss/1.0/modules/content/}encoded'))
        if not title and not text: continue
        link = official_url(node.findtext('link'), ATAC_STATUS)
        key = node.findtext('guid') or hashlib.sha256((title + text).encode()).hexdigest()[:20]
        published = timestamp(node.findtext('pubDate'))
        entries.append({'id': 'atac-' + key, 'title': title, 'text': text[:30000], 'summary': text[:360],
                        'url': link, 'source': 'ATAC', 'section': 'Stato del servizio', 'category': category(title),
                        'publishedAt': published, 'updatedAt': published, 'lines': line_mentions(title + '\n' + text), 'live': True})
    return {'entries': entries, 'sourceTimestamp': timestamp(channel.findtext('lastBuildDate')) or timestamp(channel.findtext('pubDate'))}


# IDs and labels from the home page's StatoServizioWidget routeStatuses.
# Partial interruptions must not imply that the whole line is suspended.
_HOME_STATUSES = {
    '1': ('regular', 'Regolare'), '2': ('delays', 'Rallentata'),
    '3': ('modified', 'Servizio modificato'), '6': ('modified', 'Parzialmente non attiva'),
    '4': ('suspended', 'Non attiva'), '7': ('modified', 'Riprogrammata'),
    '8': ('modified', 'Lavori programmati'), '5': ('suspended', 'Chiusa'),
}


def empty_metro_line(code):
    return {'code': code, 'name': f'Metro {code}', 'status': 'unknown', 'label': 'Stato non verificabile',
            'detail': '', 'url': ATAC_HOME, 'publishedAt': None}


def parse_metro_lines(rows):
    """Read the same line status fields and active directions as ATAC's home widget."""
    if not isinstance(rows, list): raise ValueError('Formato stato Metro non riconosciuto')
    codes = {f'METRO{code}': code for code in METRO_LINES}
    found = {}
    for row in rows:
        if not isinstance(row, dict) or str(row.get('Type')) != '1': continue
        code = codes.get(str(row.get('Code', '')).strip().upper())
        if not code: continue
        line = empty_metro_line(code)
        if code in found:
            # Conflicting/duplicate records cannot verify a line as regular.
            found[code] = line
            continue
        if row.get('IsOn') is True:
            line['status'], line['label'] = _HOME_STATUSES.get(str(row.get('Status')), ('unknown', 'Stato non verificabile'))
        details = []
        for route in row.get('Routes', []) if isinstance(row.get('Routes'), list) else []:
            if not isinstance(route, dict) or not isinstance(route.get('Schedule'), dict) or route['Schedule'].get('IsOn') is not True: continue
            name, status = plain_text(route.get('Name')), plain_text(route.get('StatusName'))
            description = plain_text(route.get('Description'))
            detail = ': '.join(value for value in (name, status) if value)
            if description and description != '-': detail += ('\n' if detail else '') + description
            if detail: details.append(detail)
        line['detail'] = '\n\n'.join(details)[:30000]
        found[code] = line
    if not found: raise ValueError('Stato Metro assente dalla fonte ATAC')
    return [found.get(code, empty_metro_line(code)) for code in METRO_LINES]


def fetch_metro():
    # The saved home HTML identifies this public JSON POST. Never use that
    # saved snapshot as current service status or infer it from RSS news.
    return parse_metro_lines(json.loads(download(ATAC_METRO, {'languageName': 'it'})))


class OfficialSource:
    """Share downloads; a slow refresh never blocks readers of a cached snapshot."""
    def __init__(self, loader, ttl=60):
        self.loader, self.ttl = loader, ttl
        self.lock = threading.Lock()
        self.value = None
        self.success = self.attempt = self.deadline = 0
        self.error, self.pending = '', False

    def snapshot(self):
        return {'data': self.value, 'timestamp': self.success or None, 'checkedAt': self.attempt or None,
                'available': self.value is not None and not self.error and time.time() - self.success <= 300,
                'stale': self.value is not None and (bool(self.error) or time.time() - self.success > 300),
                'error': self.error, 'refreshing': self.pending}

    def read(self, refresh=False):
        with self.lock:
            if self.pending or (time.monotonic() < self.deadline and (not refresh or time.time() - self.attempt < 2)):
                return self.snapshot()
            self.pending = True
            retained = self.value is not None
        if retained and not refresh:
            _workers.submit(self.update)
            with self.lock: return self.snapshot()
        return self.update()

    def update(self):
        try:
            value, error = self.loader(), ''
        except Exception:
            value, error = None, 'Fonte temporaneamente non disponibile. Riprova tra poco.'
        with self.lock:
            self.attempt = time.time()
            if not error: self.value, self.success = value, self.attempt
            self.error, self.pending = error, False
            self.deadline = time.monotonic() + (15 if error else self.ttl)
            return self.snapshot()


_sources = {kind: OfficialSource(lambda kind=kind: fetch_articles(kind)) for kind in SOURCES}
_sources['atac'] = OfficialSource(lambda: rss_entries(download(ATAC_FEED)))
_sources['atac-metro'] = OfficialSource(fetch_metro)


def news(refresh=False):
    values = [_sources[kind].read(refresh) for kind in SOURCES]
    articles = {item['id']: item for value in values for item in value['data'] or []}
    return {'articles': sorted(articles.values(), key=lambda item: (item['updatedAt'], item['id']), reverse=True),
            'available': all(value['available'] for value in values), 'partial': any(value['available'] for value in values) and not all(value['available'] for value in values),
            'stale': any(value['stale'] for value in values), 'refreshing': any(value['refreshing'] for value in values),
            'timestamp': min((value['timestamp'] for value in values if value['timestamp']), default=None),
            'error': next((value['error'] for value in values if value['error']), '')}


def metro_status(text):
    text = text.lower()
    if re.search(r'\b(?:stazion[ei]|fermat[ae])\b[^\n.]{0,70}\b(?:chius|sospes)|\bchius[ao]\b[^\n.]{0,50}\b(?:stazione|fermata)\b', text): return 'modified', 'Servizio modificato'
    if re.search(r'\b(?:interrott[oa]|sospes[oa]|chius[ao]|non attiv[ao])\b', text): return 'suspended', 'Servizio interrotto'
    if re.search(r'rallent|ritard|riduzion|ridott', text): return 'delays', 'Rallentamenti'
    if re.search(r'limitazion|limitat|modificat|variazion|sostitutiv|lavori|non regolare|irregolare|perturbat', text): return 'modified', 'Servizio modificato'
    if re.search(r'\bregolare\b|\briattivat[oa]\b|\bripristinat[oa]\b', text): return 'regular', 'Servizio regolare'
    return 'unknown', 'Stato non verificabile'


def service_feed_fresh(source):
    build_time = (source['data'] or {}).get('sourceTimestamp')
    # Service bulletins persist until the publisher changes/removes them. Their
    # publication date is not a vehicle-position TTL: a permanent diversion or
    # unchanged regular status may be old while the current RSS is verified.
    return source['available'] and (build_time is None or build_time <= time.time() + 60)


def metro(refresh=False):
    snapshot_path = os.environ.get('ATAC_METRO_SNAPSHOT', '').strip()
    if snapshot_path:
        # The browser collector refreshes this file independently of API readers.
        source = read_snapshot(snapshot_path)
        if source['data'] is not None:
            try:
                source['data'] = parse_metro_lines(source['data'])
            except ValueError:
                source.update(data=None, timestamp=None, available=False, stale=False, error=METRO_UNAVAILABLE)
    else:
        source = _sources['atac-metro'].read(refresh)
    lines = source['data'] or [empty_metro_line(code) for code in METRO_LINES]
    if not source['available']:
        lines = [line | {'status': 'unknown', 'label': 'Stato non verificabile'} for line in lines]
    return {k: v for k, v in source.items() if k != 'data'} | {
        'partial': source['available'] and any(line['status'] == 'unknown' for line in lines),
        'sourceTimestamp': None, 'lines': lines, 'source': 'ATAC', 'sourceUrl': ATAC_HOME}


def line_alerts(route_id, refresh=False):
    with t.connect() as db:
        route = db.execute('SELECT route_id,name FROM routes WHERE route_id=?', (route_id,)).fetchone()
        if not route: raise ValueError('Linea non trovata')
        name = route['name']
    # RSM reports are dated news; they never imply that an old diversion is active.
    result = news(refresh)
    bulletins = _sources['atac'].read(refresh)
    key = name.strip().upper()
    feed_fresh = service_feed_fresh(bulletins)
    official = [item for item in (bulletins['data'] or {}).get('entries', [])
                if metro_status(item['title'] + '\n' + item['text'])[0] != 'regular'] if feed_fresh else []
    items = [item for item in [*official, *result['articles']] if key in item['lines']]
    available = result['available'] and feed_fresh
    return {'line': name, 'items': items, 'timestamp': result['timestamp'],
            'available': available,
            'partial': not available and (result['available'] or result['partial'] or feed_fresh),
            'stale': result['stale'] or bulletins['stale'] or bool((bulletins['data'] or {}).get('sourceTimestamp') and not feed_fresh),
            'refreshing': result['refreshing'] or bulletins['refreshing'],
            'error': result['error'] or bulletins['error']}
