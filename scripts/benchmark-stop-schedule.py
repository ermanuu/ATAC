"""Run from /workspace/ATAC with .venv/bin/python scripts/benchmark-stop-schedule.py.
Synthetic CPU comparison, not a VM or production capacity test. No network.
"""
import json
from pathlib import Path
import sqlite3
import statistics
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from unittest.mock import patch

sys.path[:0] = [str(Path.cwd()), str(Path.cwd() / 'tests')]
from server import transit as t
from server.cache import SharedCache
from test_transit import fixture
from google.transit import gtfs_realtime_pb2 as pb

original = subprocess.check_output(['git', 'show', '61105ac:server/transit.py'], text=True)
source = original[original.index('def arrivals('):original.index('\ndef plan(')]
now = int(datetime(2026, 10, 30, 10, 0, tzinfo=t.ROME).timestamp())
feed = pb.FeedMessage(); feed.header.gtfs_realtime_version = '2.0'; feed.header.timestamp = now
for i in range(200):
    e = feed.entity.add(); e.id = str(i)
    u = e.trip_update; u.trip.trip_id = 't1' if i == 0 else f'clone{i}'
    u.timestamp = now; u.vehicle.label = str(i + 1000)
    event = u.stop_time_update.add(); event.stop_id = 'b'; event.arrival.time = now + 700 + i
live = {'available': True, 'timestamp': now, 'feed': feed}
with tempfile.TemporaryDirectory() as folder, patch.object(t, 'DATA', Path(folder)), patch.object(t, 'DB', Path(folder) / 'transit.sqlite'), patch.object(t, 'read_live', return_value=live), patch.object(t.time, 'time', return_value=now) as clock:
    t.import_gtfs(fixture())
    with sqlite3.connect(t.DB) as db:
        for i in range(1, 200):
            trip = f'clone{i}'
            db.execute("INSERT INTO trips SELECT ?,route_id,service_id,headsign,direction FROM trips WHERE trip_id='t1'", (trip,))
            db.execute("INSERT INTO times SELECT ?,stop_id,sequence,arrival,departure,pickup,dropoff FROM times WHERE trip_id='t1'", (trip,))
    namespace = dict(t.__dict__)
    exec(compile(source, '<baseline arrivals at 61105ac>', 'exec'), namespace)
    baseline = namespace['arrivals']
    for offset in range(60):
        clock.return_value = now + offset
        assert baseline('b') == t.arrivals('b'), offset
    results = {'baseline_cpu_seconds': [], 'cached_cpu_seconds': []}
    for repeat in range(5):
        order = [('baseline', baseline), ('cached', t.arrivals)]
        if repeat % 2:
            order.reverse()
        for label, function in order:
            with patch.object(t, '_stop_schedules', SharedCache(max_entries=256, max_weight=200000,
                    weight=lambda value: len(value[0]) + sum(map(len, value[1].values())))):
                started = time.process_time()
                for offset in range(60):
                    clock.return_value = now + offset
                    function('b')
                results[label + '_cpu_seconds'].append(round(time.process_time() - started, 6))
    before = statistics.median(results['baseline_cpu_seconds'])
    after = statistics.median(results['cached_cpu_seconds'])
    results.update({'baseline_commit': '61105ac', 'workload': 'Synthetic GTFS: 200 trips at one stop, 200 fresh live updates; 60 calls at successive seconds, five alternating trials; trip patterns prewarmed; static minute cache cold each trial.', 'equivalent_responses': 60, 'cpu_reduction_percent': round((1-after/before)*100, 2), 'limitations': 'In-process CPU only. No HTTP, public feeds, VM, Caddy, TLS or 10000-user capacity validation.'})
    print(json.dumps(results, indent=2))
