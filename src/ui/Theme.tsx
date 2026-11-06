import AsyncStorage from '@react-native-async-storage/async-storage';
import React, { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react';
import { Platform, useColorScheme } from 'react-native';

export type ThemePreference = 'system' | 'light' | 'dark';
type ColorScheme = 'light' | 'dark';
export type ThemeColors = typeof palettes.light;

const palettes = {
  light: {
    background: '#f7f8fa', surface: '#ffffff', surfaceAlt: '#f0f2f5',
    backgroundGradient: ['#f8e9ed', '#f5f4f8', '#e4eff1'] as [string, string, string],
    sphereRed: ['rgba(196,58,96,0.14)', 'rgba(239,187,199,0.02)'] as [string, string],
    sphereBlue: ['rgba(164,204,217,0.22)', 'rgba(222,242,244,0.02)'] as [string, string],
    text: '#1a202c', muted: '#536173', placeholder: '#667487', border: '#dce1e8',
    accent: '#96002d', accentFill: '#96002d', onAccent: '#ffffff',
    accentSoft: '#fbe9ef', pressed: '#f3d6df', disabled: '#e3e6eb',
    live: '#167450', liveSoft: '#e2f3e9', rail: '#16845e',
    shadow: '0 3px 12px rgba(27,34,48,0.05)', floatingShadow: '0 5px 20px rgba(27,34,48,0.12)',
  },
  dark: {
    background: '#090f1c', surface: '#172131', surfaceAlt: '#111a29',
    backgroundGradient: ['#1a1322', '#090f1c', '#101e2c'] as [string, string, string],
    sphereRed: ['rgba(211,60,82,0.20)', 'rgba(211,60,82,0.02)'] as [string, string],
    sphereBlue: ['rgba(86,138,175,0.18)', 'rgba(86,138,175,0.02)'] as [string, string],
    text: '#f6f2ed', muted: '#b2bdce', placeholder: '#9caac0', border: '#334156',
    accent: '#ff6b6b', accentFill: '#bf123d', onAccent: '#ffffff',
    accentSoft: '#351b2b', pressed: '#4b2335', disabled: '#293549',
    live: '#70dba2', liveSoft: '#14362d', rail: '#70dba2',
    shadow: '0 3px 12px rgba(0,0,0,0.12)', floatingShadow: '0 5px 20px rgba(0,0,0,0.3)',
  },
};
const STORAGE_KEY = 'romabus-theme';
const isPreference = (value: unknown): value is ThemePreference => value === 'system' || value === 'light' || value === 'dark';
type ThemeState = { preference: ThemePreference; scheme: ColorScheme; colors: ThemeColors; setPreference: (value: ThemePreference) => void; storageError: string };
const ThemeContext = createContext<ThemeState>({ preference: 'system', scheme: 'light', colors: palettes.light, setPreference: () => {}, storageError: '' });

export function ThemeProvider({ children }: React.PropsWithChildren) {
  const systemScheme = useColorScheme();
  const [preference, updatePreference] = useState<ThemePreference>('system');
  const [ready, setReady] = useState(false);
  const [storageError, setStorageError] = useState('');
  const writes = useRef(Promise.resolve());
  useEffect(() => {
    let active = true;
    AsyncStorage.getItem(STORAGE_KEY).then(value => {
      if (active && isPreference(value)) updatePreference(value);
    }).catch(() => {
      if (active) setStorageError('Impossibile recuperare il tema salvato su questo dispositivo.');
    }).finally(() => { if (active) setReady(true); });
    return () => { active = false; };
  }, []);
  const setPreference = useCallback((value: ThemePreference) => {
    updatePreference(value);
    // Keep the last choice even when storage is slower than successive taps.
    writes.current = writes.current.then(() => AsyncStorage.setItem(STORAGE_KEY, value))
      .then(() => setStorageError(''))
      .catch(() => setStorageError('Il tema è attivo, ma non è stato possibile salvare la scelta.'));
  }, []);
  const scheme: ColorScheme = preference === 'system' ? systemScheme === 'dark' ? 'dark' : 'light' : preference;
  const colors = palettes[scheme];
  useEffect(() => {
    if (Platform.OS !== 'web' || !ready) return;
    document.documentElement.style.colorScheme = scheme;
    document.documentElement.style.setProperty('--romabus-background', colors.background);
    document.querySelector('meta[name="theme-color"]')?.setAttribute('content', colors.background);
  }, [scheme, colors, ready]);
  const value = useMemo(() => ({ preference, scheme, colors, setPreference, storageError }), [preference, scheme, colors, setPreference, storageError]);
  return <ThemeContext.Provider value={value}>{ready ? children : null}</ThemeContext.Provider>;
}

export const useTheme = () => useContext(ThemeContext);
