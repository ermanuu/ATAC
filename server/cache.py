"""Bounded process-local caches that share an in-flight calculation per key."""
from collections import OrderedDict
from concurrent.futures import Future
import asyncio
import threading
import time


class CacheBusy(Exception):
    pass


class SharedCache:
    def __init__(self, max_entries=128, max_weight=16 * 1024 * 1024, weight=lambda value: 1):
        self.max_entries = max_entries
        self.max_weight = max_weight
        self.weight = weight
        self.entries = OrderedDict()
        self.pending = {}
        self.total_weight = 0
        self.lock = threading.Lock()

    def claim(self, key):
        with self.lock:
            now = time.monotonic()
            for expired, (_, deadline, weight) in list(self.entries.items()):
                if deadline <= now:
                    del self.entries[expired]
                    self.total_weight -= weight
            if key in self.entries:
                self.entries.move_to_end(key)
                return self.entries[key][0], None, False
            pending = self.pending.get(key)
            owner = pending is None
            if owner:
                pending = self.pending[key] = Future()
        return None, pending, owner

    def compute(self, key, pending, build, ttl):
        try:
            value = build()
            weight = self.weight(value)
            with self.lock:
                if weight <= self.max_weight:
                    self.entries[key] = (value, time.monotonic() + ttl, weight)
                    self.total_weight += weight
                    while len(self.entries) > self.max_entries or self.total_weight > self.max_weight:
                        _, (_, _, removed) = self.entries.popitem(last=False)
                        self.total_weight -= removed
                del self.pending[key]
            pending.set_result(value)
            return value
        except BaseException as exc:
            with self.lock:
                self.pending.pop(key, None)
            pending.set_exception(exc)
            raise

    def get(self, key, build, ttl, wait=True):
        value, pending, owner = self.claim(key)
        if pending is None:
            return value
        if not owner:
            if not wait:
                raise CacheBusy('Calcolo già in corso')
            return pending.result()
        return self.compute(key, pending, build, ttl)

    async def get_async(self, key, build, ttl, executor, wait=True):
        value, pending, owner = self.claim(key)
        if pending is None:
            return value
        if not owner and not wait:
            raise CacheBusy('Calcolo già in corso')
        if owner:
            try:
                job = executor.submit(self.compute, key, pending, build, ttl)

                def cancelled(future):
                    if future.cancelled():
                        with self.lock:
                            if self.pending.get(key) is pending:
                                del self.pending[key]
                        pending.cancel()

                job.add_done_callback(cancelled)
            except Exception as exc:
                with self.lock:
                    self.pending.pop(key, None)
                pending.set_exception(exc)
        wrapped = asyncio.wrap_future(pending)
        # A disconnected client must not cancel the calculation shared by
        # other readers. Also retrieve a later exception if all clients leave.
        wrapped.add_done_callback(lambda future: future.exception() if not future.cancelled() else None)
        return await asyncio.shield(wrapped)
