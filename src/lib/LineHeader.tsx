import React, { createContext, useCallback, useContext, useState } from 'react';

type LineTitle = { routeId: string; variant: string; line: string; direction: string };
const LineHeaderContext = createContext<{ title: LineTitle | null; publish: (title: LineTitle) => void }>({ title: null, publish: () => {} });
export function LineHeaderProvider({ children }: React.PropsWithChildren) {
  const [title, setTitle] = useState<LineTitle | null>(null);
  const publish = useCallback((next: LineTitle) => {
    setTitle(current => current?.routeId === next.routeId && current.variant === next.variant && current.line === next.line && current.direction === next.direction ? current : next);
  }, []);
  return <LineHeaderContext.Provider value={{ title, publish }}>{children}</LineHeaderContext.Provider>;
}
export const useLineHeader = () => useContext(LineHeaderContext);
