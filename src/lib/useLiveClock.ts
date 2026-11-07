import { useCallback, useState } from 'react';
import { AppState } from 'react-native';
import { useFocusEffect } from 'expo-router';

/** Expire live predictions only while their screen is in the foreground. */
export function useLiveClock(enabled = true) {
  const [now, setNow] = useState(() => Date.now() / 1000);
  useFocusEffect(useCallback(() => {
    if (!enabled) return;
    let timer: ReturnType<typeof setInterval> | undefined;
    const stop = () => { if (timer) { clearInterval(timer); timer = undefined; } };
    const start = () => { stop(); timer = setInterval(() => setNow(Date.now() / 1000), 10000); };
    if (AppState.currentState !== 'background' && AppState.currentState !== 'inactive') start();
    const listener = AppState.addEventListener('change', state => {
      if (state === 'active') { setNow(Date.now() / 1000); start(); }
      else stop();
    });
    return () => { stop(); listener?.remove(); };
  }, [enabled]));
  return now;
}
