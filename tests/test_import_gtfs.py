"""Scheduled and manual imports must not overwrite each other's temporary DB."""
import os
from pathlib import Path
import select
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from server import import_gtfs as cli
from server import transit


@unittest.skipUnless(os.name == 'posix', 'Linux deployment lock')
class ImportLockTests(unittest.TestCase):
    def test_another_process_waits_until_import_finishes(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(transit, 'DATA', Path(folder)):
            with cli.import_lock():
                child = subprocess.Popen([
                    sys.executable, '-c',
                    "from pathlib import Path; import sys; "
                    "from server import transit; from server.import_gtfs import import_lock; "
                    "transit.DATA=Path(sys.argv[1]); print('waiting',flush=True)\n"
                    "with import_lock(): print('acquired',flush=True)", folder,
                ], cwd=Path(__file__).resolve().parents[1], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                try:
                    self.assertTrue(select.select([child.stdout], [], [], 5)[0])
                    self.assertEqual(child.stdout.readline(), 'waiting\n')
                    self.assertFalse(select.select([child.stdout], [], [], 0.2)[0])
                except BaseException:
                    child.kill()
                    child.communicate()
                    raise
            try:
                output, errors = child.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                child.kill()
                child.communicate()
                raise
            self.assertEqual(child.returncode, 0, errors)
            self.assertEqual(output, 'acquired\n')

    def test_cli_holds_lock_during_download_and_releases_it_after_failure(self):
        import fcntl
        with tempfile.TemporaryDirectory() as folder, patch.object(transit, 'DATA', Path(folder)):
            def failing_download(url):
                with (Path(folder) / '.import.lock').open('a') as probe:
                    with self.assertRaises(BlockingIOError):
                        fcntl.flock(probe, fcntl.LOCK_EX | fcntl.LOCK_NB)
                raise OSError('feed unavailable')

            with patch.object(transit, 'download', side_effect=failing_download):
                with self.assertRaisesRegex(OSError, 'feed unavailable'):
                    cli.main()
            with (Path(folder) / '.import.lock').open('a') as probe:
                fcntl.flock(probe, fcntl.LOCK_EX | fcntl.LOCK_NB)
