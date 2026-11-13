import os
from pathlib import Path
import subprocess
import shutil
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts/install-metro-browser.sh'


@unittest.skipUnless(sys.platform.startswith('linux') and shutil.which('bash'), 'Linux installer only')
class MetroInstallTests(unittest.TestCase):
    def test_shell_syntax(self):
        subprocess.run(['bash', '-n', str(SCRIPT)], check=True)
        subprocess.run(['bash', '-n', str(ROOT / 'scripts/verify-metro-browser.sh')], check=True)

    def test_manual_verification_checks_x11_before_stopping_services(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            calls = root / 'systemctl-calls'
            command = root / 'systemctl'
            command.write_text('#!/bin/sh\nprintf called > "$ROMABUS_TEST_CALLS"\n')
            command.chmod(0o755)
            env = os.environ | {'DISPLAY': '', 'ROMABUS_TEST_CALLS': str(calls),
                                'PATH': folder + os.pathsep + os.environ['PATH']}
            result = subprocess.run(['bash', str(ROOT / 'scripts/verify-metro-browser.sh')],
                                    env=env, text=True, capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('DISPLAY assente', result.stderr)
            self.assertFalse(calls.exists())

    def test_staging_is_idempotent_and_leaves_the_existing_web_service_intact(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            web = root / 'etc/systemd/system/romabus.service'
            web.parent.mkdir(parents=True)
            web.write_text('existing service')
            env = os.environ | {'DESTDIR': folder}
            for _ in range(2):
                result = subprocess.run(['bash', str(SCRIPT)], env=env, check=True, text=True, capture_output=True)
                self.assertIn('nessun servizio attivato', result.stdout)
            self.assertEqual(web.read_text(), 'existing service')
            service = root / 'etc/systemd/system/romabus-metro-browser.service'
            self.assertIn('User=romabus', service.read_text())
            self.assertIn('Type=notify', service.read_text())
            self.assertIn('RestartPreventExitStatus=3', service.read_text())
            self.assertIn('scripts/watch-atac-metro.py', service.read_text())
            self.assertIn('--output /opt/romabus/server/data/metro-browser.json', service.read_text())
            timer = root / 'etc/systemd/system/romabus-metro-browser.timer'
            self.assertFalse(timer.exists())
            dropin = root / 'etc/systemd/system/romabus.service.d/metro-browser.conf'
            self.assertIn('ATAC_METRO_SNAPSHOT=', dropin.read_text())
            self.assertFalse(list(root.rglob('*.backup.*')))
            self.assertFalse((root / 'var/lib').exists())

    def test_changed_existing_config_is_backed_up(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            target = root / 'etc/systemd/system/romabus.service.d/metro-browser.conf'
            target.parent.mkdir(parents=True)
            target.write_text('previous config')
            subprocess.run(['bash', str(SCRIPT)], env=os.environ | {'DESTDIR': folder}, check=True, capture_output=True)
            backups = list(target.parent.glob('metro-browser.conf.backup.*'))
            self.assertEqual(len(backups), 1)
            self.assertEqual(backups[0].read_text(), 'previous config')

    def test_relative_staging_path_is_rejected(self):
        result = subprocess.run(['bash', str(SCRIPT)], env=os.environ | {'DESTDIR': 'relative'}, capture_output=True)
        self.assertNotEqual(result.returncode, 0)
