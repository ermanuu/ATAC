"""Simulate polling visitors with bounded, reusable HTTP connections."""
import argparse
import asyncio
import json
import math
from pathlib import Path
import statistics
from urllib.parse import quote

import aiohttp
from aiohttp.helpers import get_env_proxy_for_url
from yarl import URL


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', default='http://127.0.0.1:8000')
    parser.add_argument('--users', type=int, default=100)
    parser.add_argument('--duration', type=float, default=60)
    parser.add_argument('--interval', type=float, default=10)
    parser.add_argument('--connections', type=int, default=256,
                        help='Maximum active HTTP requests; independent of virtual users (default: 256)')
    parser.add_argument('--timeout', type=float, default=20,
                        help='Seconds allowed for client queueing and the HTTP request together')
    parser.add_argument('--lines', default='706,714,64,40,90')
    parser.add_argument('--paths-file', type=Path, help='JSON list of API paths, avoiding catalog warm-up')
    parser.add_argument('--burst', action='store_true', help='Start all visitors together instead of spreading their first polls')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args(argv)
    if not 1 <= args.users <= 10000:
        parser.error('Use 1–10000 virtual users.')
    if not 1 <= args.connections <= 10000:
        parser.error('Use 1–10000 connections.')
    if any(not math.isfinite(value) or value <= 0 for value in (args.duration, args.interval, args.timeout)):
        parser.error('Use finite, positive duration, interval and timeout.')
    return args


def timings(samples):
    ordered = sorted(samples)

    def percentile(fraction):
        return round(ordered[max(0, math.ceil(len(ordered) * fraction) - 1)] * 1000, 1) if ordered else None

    return {'median': round(statistics.median(samples) * 1000, 1) if samples else None,
            'p95': percentile(.95), 'p99': percentile(.99), 'max': percentile(1)}


async def discover(args, request):
    if args.paths_file:
        paths = json.loads(args.paths_file.read_text())
        if not isinstance(paths, list) or not paths or not all(isinstance(path, str) and path.startswith('/api/') for path in paths):
            raise ValueError('--paths-file must contain a nonempty JSON list of /api/ paths.')
        return paths
    paths = []
    for line in (value.strip() for value in args.lines.split(',')):
        routes = await request('/api/routes?q=' + quote(line))
        route = next((route for route in routes if route['name'] == line), None)
        if not route:
            continue
        route_path = '/api/routes/' + quote(route['route_id'], safe='')
        directions = (await request(route_path))['variants']
        if not directions:
            continue
        board_path = route_path + '?variant=' + directions[0]['id']
        board = await request(board_path)
        paths.append(board_path)
        stop = board['stops'][len(board['stops']) // 2]['stop_id']
        paths.append('/api/stops/' + quote(stop, safe='') + '/arrivals')
    if not paths:
        raise ValueError('No active lines found. Use --lines or --paths-file.')
    print('Catalog and sample boards loaded before the measurement.', flush=True)
    return paths


async def run_load(args, paths, request, progress=None):
    loop = asyncio.get_running_loop()
    started = loop.time()
    end = started + args.duration
    connections = asyncio.Semaphore(args.connections)
    samples, http_samples, queue_samples, lag_samples = [], [], [], []
    error_examples = []
    sent = completed = errors = queue_timeouts = sent_in_window = 0
    done = asyncio.Event()

    async def visitor(index):
        nonlocal sent, completed, errors, queue_timeouts, sent_in_window
        path = paths[index % len(paths)]
        deadline = started if args.burst else started + args.interval * index / args.users
        first = True
        while deadline < end:
            await asyncio.sleep(max(0, deadline - loop.time()))
            ready = loop.time()
            lag_samples.append(max(0, ready - deadline))
            wire_started = None
            queued = None

            async def send():
                nonlocal wire_started, queued, sent, sent_in_window
                async with connections:
                    wire_started = loop.time()
                    queued = wire_started - ready
                    sent += 1
                    if wire_started < end:
                        sent_in_window += 1
                    current = path + ('&' if '?' in path else '?') + 'fresh=1' if first else path
                    await request(current)

            try:
                # Include the semaphore wait: overload cannot leave an
                # unlimited client backlog outside the HTTP timeout.
                await asyncio.wait_for(send(), timeout=args.timeout)
            except (aiohttp.ClientError, OSError, ValueError, asyncio.TimeoutError) as exc:
                if wire_started is None:
                    queue_timeouts += 1
                    kind = 'client_queue_timeout'
                else:
                    errors += 1
                    kind = 'http_request'
                if len(error_examples) < 10:
                    error_examples.append({'path': path, 'kind': kind, 'error': f'{type(exc).__name__}: {exc}'})
            finished = loop.time()
            samples.append(finished - ready)
            queue_samples.append(queued if queued is not None else finished - ready)
            if wire_started is not None:
                completed += 1
                http_samples.append(finished - wire_started)
            first = False
            deadline += args.interval
            # Like the app, a visitor never overlaps a slow request with its
            # next poll. Report missed load instead of hiding the slowdown.
            if deadline < finished:
                deadline += math.ceil((finished - deadline) / args.interval) * args.interval

    async def monitor():
        while not done.is_set():
            try:
                await asyncio.wait_for(done.wait(), timeout=10)
            except asyncio.TimeoutError:
                if progress:
                    progress(f'{loop.time() - started:.0f}s: {completed} requests, {errors} HTTP errors, {queue_timeouts} client queue timeouts')

    monitor_task = asyncio.create_task(monitor())
    try:
        await asyncio.gather(*(visitor(index) for index in range(args.users)))
        # Bursts also measure the full configured window; requests already
        # in progress may finish afterwards and appear in drain_seconds.
        await asyncio.sleep(max(0, end - loop.time()))
    finally:
        done.set()
        await monitor_task
    elapsed = loop.time() - started
    expected = (args.users * math.ceil(args.duration / args.interval) if args.burst else
                math.ceil(args.duration * args.users / args.interval))
    missed = max(0, expected - sent_in_window)
    return {'users': args.users, 'connections': args.connections, 'endpoints': len(paths),
            'interval_seconds': args.interval, 'burst': args.burst,
            'scheduled_duration_seconds': args.duration, 'duration_seconds': round(elapsed, 2),
            'drain_seconds': round(max(0, elapsed - args.duration), 2),
            'target_requests_per_second': round(expected / args.duration, 2),
            'expected_requests': expected, 'requests': sent, 'errors': errors,
            'requests_started_in_window': sent_in_window, 'missed_requests': missed,
            'generator_queue_timeouts': queue_timeouts,
            'load_target_met': sent_in_window >= expected * .99,
            'requests_per_second': round(completed / elapsed, 2),
            'offered_requests_per_second': round(sent_in_window / args.duration, 2),
            'latency_ms': timings(samples), 'http_latency_ms': timings(http_samples),
            'client_queue_ms': timings(queue_samples), 'scheduler_lag_ms': timings(lag_samples),
            'error_examples': error_examples}


async def run(args):
    # The origin stays fixed. Resolve the normal environment proxy once, using
    # aiohttp's resolver, rather than doing blocking env/netrc work per poll.
    try:
        proxy, proxy_auth = await asyncio.to_thread(get_env_proxy_for_url, URL(args.base_url))
    except LookupError:
        proxy, proxy_auth = None, None
    connector = aiohttp.TCPConnector(limit=args.connections, limit_per_host=args.connections)
    async with aiohttp.ClientSession(connector=connector, timeout=aiohttp.ClientTimeout(total=args.timeout),
                                     headers={'Accept-Encoding': 'gzip'}) as session:
        async def request(path):
            async with session.get(args.base_url.rstrip('/') + path, proxy=proxy, proxy_auth=proxy_auth) as result:
                await result.read()
                result.raise_for_status()
                return await result.json()

        paths = await discover(args, request)
        print(f'{args.users} virtual visitors, {len(paths)} endpoints, one poll per {args.interval:g} s; '
              f'duration {args.duration:g} s, at most {args.connections} HTTP requests in flight.', flush=True)
        report = await run_load(args, paths, request, progress=lambda value: print(value, flush=True))
    print(json.dumps(report, indent=2), flush=True)
    if not report['load_target_met']:
        print('Requested load was not reached: fewer than 99% of scheduled polls started in the measurement window.', flush=True)
    if args.output:
        args.output.write_text(json.dumps(report, indent=2) + '\n')
    return 1 if report['errors'] or report['generator_queue_timeouts'] or not report['load_target_met'] else 0


def main(argv=None):
    args = parse_args(argv)
    try:
        return asyncio.run(run(args))
    except (aiohttp.ClientError, OSError, ValueError) as exc:
        raise SystemExit(f'Cannot prepare load test: {exc}') from exc


if __name__ == '__main__':
    raise SystemExit(main())
