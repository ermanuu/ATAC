import AsyncStorage from '@react-native-async-storage/async-storage';
import React, { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react';
import { parseRecentLines, rememberRecentLine, type RecentLine } from './recentLines';

export type HomeContent = 'recent-lines' | 'favorite-stops';
const CONTENT_KEY = 'romabus-home-content';
const HISTORY_KEY = 'recent-lines';
type HomePreferences = {
  content: HomeContent;
  setContent: (value: HomeContent) => void;
  recentLines: RecentLine[];
  rememberLine: (route: RecentLine) => Promise<void>;
  storageError: string;
  historyError: string;
};
const HomeContext = createContext<HomePreferences>({ content: 'recent-lines', setContent: () => {}, recentLines: [], rememberLine: () => Promise.resolve(), storageError: '', historyError: '' });

export function HomePreferencesProvider({ children }: React.PropsWithChildren) {
  const [content, updateContent] = useState<HomeContent>('recent-lines');
  const [recentLines, setRecentLines] = useState<RecentLine[]>([]);
  const [storageError, setStorageError] = useState('');
  const [historyError, setHistoryError] = useState('');
  const [ready, setReady] = useState(false);
  const recent = useRef<RecentLine[]>([]);
  const contentWrites = useRef(Promise.resolve());
  const historyWrites = useRef(Promise.resolve());
  useEffect(() => {
    let active = true;
    void Promise.allSettled([AsyncStorage.getItem(CONTENT_KEY), AsyncStorage.getItem(HISTORY_KEY)]).then(([preference, history]) => {
      if (!active) return;
      if (preference.status === 'fulfilled') {
        if (preference.value === 'recent-lines' || preference.value === 'favorite-stops') updateContent(preference.value);
      } else setStorageError('Impossibile recuperare la scelta salvata per la home.');
      if (history.status === 'fulfilled') {
        recent.current = parseRecentLines(history.value);
        setRecentLines(recent.current);
      } else setHistoryError('Impossibile recuperare le ultime linee cercate.');
      setReady(true);
    });
    return () => { active = false; };
  }, []);
  const setContent = useCallback((value: HomeContent) => {
    updateContent(value);
    contentWrites.current = contentWrites.current.then(() => AsyncStorage.setItem(CONTENT_KEY, value))
      .then(() => setStorageError(''))
      .catch(() => setStorageError('La scelta è attiva, ma non è stato possibile salvarla su questo dispositivo.'));
  }, []);
  const rememberLine = useCallback((route: RecentLine) => {
    const next = rememberRecentLine(recent.current, route);
    recent.current = next;
    setRecentLines(next);
    historyWrites.current = historyWrites.current.then(() => AsyncStorage.setItem(HISTORY_KEY, JSON.stringify(next)))
      .then(() => setHistoryError(''))
      .catch(() => setHistoryError('Impossibile salvare le ultime linee cercate su questo dispositivo.'));
    return historyWrites.current;
  }, []);
  const value = useMemo(() => ({ content, setContent, recentLines, rememberLine, storageError, historyError }), [content, setContent, recentLines, rememberLine, storageError, historyError]);
  return <HomeContext.Provider value={value}>{ready ? children : null}</HomeContext.Provider>;
}

export const useHomePreferences = () => useContext(HomeContext);
