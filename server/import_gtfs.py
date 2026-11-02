"""Import official schedules, serializing CLI imports on Linux."""
from contextlib import contextmanager
import os

from . import transit


@contextmanager
def import_lock():
    transit.DATA.mkdir(parents=True, exist_ok=True)
    with (transit.DATA / '.import.lock').open('a') as lock:
        if os.name == 'posix':
            import fcntl
            fcntl.flock(lock, fcntl.LOCK_EX)
        yield


def main():
    with import_lock():
        print(f"Download GTFS ufficiale: {transit.STATIC_URL}", flush=True)
        transit.import_gtfs(transit.download(transit.STATIC_URL))
        print("GTFS importato e verificato.")

if __name__ == "__main__":
    main()
