import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

// This export always talks to its own host; leave the native .env untouched.
const result = spawnSync(process.execPath, [fileURLToPath(new URL('../node_modules/expo/bin/cli', import.meta.url)), 'export', '--platform', 'web'], {
  stdio: 'inherit',
  env: { ...process.env, EXPO_NO_DOTENV: '1', EXPO_PUBLIC_API_URL: '', EXPO_NO_TELEMETRY: '1' },
});
if (result.error) console.error(result.error.message);
process.exit(result.status ?? 1);
