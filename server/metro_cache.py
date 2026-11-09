"""Atomic public Metro snapshots shared by the browser collector and the API."""
import json
import math
import os
from pathlib import Path
import tempfile
import time


SOURCE = 'https://www.atac.roma.it/'
MAX_SIZE = 4 * 1024 * 1024
MAX_AGE = 300
UNAVAILABLE = 'Fonte Metro temporaneamente non verificabile. Riprova tra poco.'


def _document(path):
    with Path(path).open('rb') as handle:
        body = handle.read(MAX_SIZE + 1)
    if len(body) > MAX_SIZE:
        raise ValueError('Snapshot Metro troppo grande')
    value = json.loads(body)
    if not isinstance(value, dict) or type(value.get('version')) is not int or value['version'] != 1 or value.get('sourceUrl') != SOURCE:
        raise ValueError('Snapshot Metro non riconosciuto')
    return value


def _timestamp(value, now):
    if type(value) not in (int, float) or not math.isfinite(value) or value <= 0 or value > now + 5:
        return None
    return value


def read_snapshot(path, *, now=None):
    """Reading/copying a file never renews the time of the original download."""
    now = time.time() if now is None else now
    empty = {'data': None, 'timestamp': None, 'checkedAt': None, 'available': False,
             'stale': False, 'refreshing': False, 'error': UNAVAILABLE}
    try:
        value = _document(path)
    except (OSError, ValueError, TypeError):
        return empty
    fetched = _timestamp(value.get('fetchedAt'), now)
    checked = _timestamp(value.get('checkedAt'), now)
    rows = value.get('rows')
    if not isinstance(rows, list) or not rows:
        rows = None
    available = bool(rows is not None and fetched is not None and checked is not None
                     and fetched <= checked and now - fetched <= MAX_AGE
                     and value.get('available') is True and not value.get('error'))
    return empty | {'data': rows, 'timestamp': fetched, 'checkedAt': checked,
                    'available': available, 'stale': rows is not None and not available,
                    'error': '' if available else UNAVAILABLE}


def write_snapshot(path, rows=None, *, fetched_at=None, now=None):
    """A failed collection preserves old details and dates, and removes live status."""
    path = Path(path)
    now = time.time() if now is None else now
    previous = read_snapshot(path, now=now)
    success = rows is not None
    if success:
        if not isinstance(rows, list) or not rows:
            raise ValueError('Snapshot Metro senza linee')
        fetched_at = now if fetched_at is None else _timestamp(fetched_at, now)
        if fetched_at is None or now - fetched_at > MAX_AGE:
            raise ValueError('Data della verifica Metro non valida')
    else:
        rows, fetched_at = previous['data'], previous['timestamp']
    value = {'version': 1, 'sourceUrl': SOURCE, 'rows': rows, 'fetchedAt': fetched_at,
             'checkedAt': now, 'available': success, 'error': '' if success else UNAVAILABLE}
    body = json.dumps(value, ensure_ascii=False, allow_nan=False).encode()
    if len(body) > MAX_SIZE:
        raise ValueError('Snapshot Metro troppo grande')
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=path.name + '.', delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(body)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return value
