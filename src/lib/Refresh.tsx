import React, { createContext, useCallback, useContext, useRef, useState } from 'react';

type Loader = (force?: boolean) => Promise<void>;
const RefreshContext = createContext<{ register: (loader: Loader) => () => void; refresh: () => Promise<void>; refreshing: boolean }>({ register: () => () => {}, refresh: async () => {}, refreshing: false });
export function RefreshProvider({ children }: React.PropsWithChildren) {
  const loaders = useRef(new Set<Loader>());
  const running = useRef<Promise<void> | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const register = useCallback((loader: Loader) => { loaders.current.add(loader); return () => { loaders.current.delete(loader); }; }, []);
  const refresh = useCallback(() => {
    if (running.current) return running.current;
    setRefreshing(true);
    const task = Promise.allSettled([...loaders.current].map(load => load(true))).then(() => {}).finally(() => { running.current = null; setRefreshing(false); });
    running.current = task;
    return task;
  }, []);
  return <RefreshContext.Provider value={{ register, refresh, refreshing }}>{children}</RefreshContext.Provider>;
}
export const useRefresh = () => useContext(RefreshContext);
