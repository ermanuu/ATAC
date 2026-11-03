#!/usr/bin/env python3
"""Simulate polling visitors against a running instance (localhost by default)."""
import argparse
from concurrent.futures import ThreadPoolExecutor, wait
import gzip
import json
import math
from pathlib import Path
import statistics
import threading
import time
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', default='http://127.0.0.1:8000')
    parser.add_argument('--users', type=int, default=100)
    parser.add_argument('--duration', type=float, default=60)
    parser.add_argument('--interval', type=float, default=10)
    parser.add_argument('--lines', default='706,714,64,40,90')
    parser.add_argument('--paths-file', type=Path, help='JSON list of API paths, avoiding catalog warm-up')
    parser.add_argument('--burst', action='store_true', help='Start all visitors together instead of spreading their first polls')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if not 1 <= args.users <= 1000 or min(args.duration, args.interval) <= 0:
        parser.error('Use 1–1000 users and positive duration/interval.')
    base = args.base_url.rstrip('/')

    def request(path):
        with urlopen(Request(base + path, headers={'Accept-Encoding': 'gzip'}), timeout=20) as result:
            body = result.read()
            if result.headers.get('Content-Encoding') == 'gzip':
                body = gzip.decompress(body)
            return json.loads(body)

    if args.paths_file:
        paths = json.loads(args.paths_file.read_text())
        if not isinstance(paths, list) or not paths or not all(isinstance(path, str) and path.startswith('/api/') for path in paths):
            parser.error('--paths-file must contain a nonempty JSON list of /api/ paths.')
    else:
        paths = []
        for line in args.lines.split(','):
            routes = request('/api/routes?q=' + quote(line))
            route = next((route for route in routes if route['name'] == line), None)
            if not route:
                continue
            route_path = '/api/routes/' + quote(route['route_id'], safe='')
            directions = request(route_path)['variants']
            if not directions:
                continue
            board_path = route_path + '?variant=' + directions[0]['id']
            board = request(board_path)
            paths.append(board_path)
            stop = board['stops'][len(board['stops']) // 2]['stop_id']
            paths.append('/api/stops/' + quote(stop, safe='') + '/arrivals')
        if not paths:
            parser.error('No active lines found. Use --lines or --paths-file.')
        print('Catalog and sample boards loaded before the measurement.', flush=True)

    started = time.monotonic()
    lock = threading.Lock()
    samples, errors = [], []

    def visitor(index):
        path = paths[index % len(paths)]
        deadline = started if args.burst else started + args.interval * index / args.users
        first = True
        while deadline < started + args.duration:
            time.sleep(max(0, deadline - time.monotonic()))
            before = time.monotonic()
            try:
                current = path + ('&' if '?' in path else '?') + 'fresh=1' if first else path
                request(current)
                failure = None
            except (HTTPError, OSError, ValueError) as exc:
                failure = f'{type(exc).__name__}: {exc}'
            elapsed = time.monotonic() - before
            with lock:
                samples.append(elapsed)
                if failure:
                    errors.append({'path': path, 'error': failure})
            first = False
            deadline += args.interval
            if deadline < time.monotonic():
                deadline = time.monotonic() + args.interval

    print(f'{args.users} visitors, {len(paths)} endpoints, one poll per {args.interval:g} s; duration {args.duration:g} s.', flush=True)
    with ThreadPoolExecutor(max_workers=args.users) as pool:
        futures = [pool.submit(visitor, index) for index in range(args.users)]
        pending = set(futures)
        while pending:
            _, pending = wait(pending, timeout=10)
            print(f'{time.monotonic() - started:.0f}s: {len(samples)} requests, {len(errors)} errors', flush=True)
        for future in futures:
            future.result()
    elapsed = time.monotonic() - started
    ordered = sorted(samples)

    def percentile(fraction):
        return round(ordered[max(0, math.ceil(len(ordered) * fraction) - 1)] * 1000, 1) if ordered else None

    report = {'users': args.users, 'endpoints': len(paths), 'interval_seconds': args.interval,
              'burst': args.burst, 'duration_seconds': round(elapsed, 2), 'requests': len(samples),
              'errors': len(errors), 'requests_per_second': round(len(samples) / elapsed, 2),
              'latency_ms': {'median': round(statistics.median(samples) * 1000, 1) if samples else None,
                             'p95': percentile(.95), 'p99': percentile(.99), 'max': percentile(1)},
              'error_examples': errors[:10]}
    print(json.dumps(report, indent=2), flush=True)
    if args.output:
        args.output.write_text(json.dumps(report, indent=2) + '\n')
    return 1 if errors else 0


if __name__ == '__main__':
    raise SystemExit(main())
