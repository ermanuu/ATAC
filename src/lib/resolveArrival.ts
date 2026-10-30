export type ArrivalReference = { routeId?: string; variantId?: string; line: string; headsign: string };
type Route = { route_id: string; name: string };
type Directions = { variants: { id?: string; headsign: string }[] };
type Request = <T>(path: string, signal?: AbortSignal) => Promise<T>;
type Destination = { pathname: '/line/[id]/[variant]'; params: { id: string; variant: string } }
  | { pathname: '/line/[id]'; params: { id: string } }
  | { pathname: '/lines'; params: { query: string } };
const normalized = (value: string) => value.trim().toLocaleLowerCase('it-IT');

// Older backends omit routeId/variantId. Rows must still open a real route or a choice.
export async function resolveArrivalDestination(arrival: ArrivalReference, request: Request, signal?: AbortSignal): Promise<Destination> {
  if (arrival.routeId && arrival.variantId) return { pathname: '/line/[id]/[variant]', params: { id: arrival.routeId, variant: arrival.variantId } };
  let routeId = arrival.routeId;
  if (!routeId) {
    const routes = await request<Route[]>(`routes?q=${encodeURIComponent(arrival.line)}`, signal);
    const exact = routes.filter(route => normalized(route.name) === normalized(arrival.line));
    if (!exact.length) throw new Error(`Itinerario della linea ${arrival.line} non trovato. Aggiorna gli orari e riprova.`);
    if (exact.length > 1) return { pathname: '/lines', params: { query: arrival.line } };
    routeId = exact[0].route_id;
  }
  const detail = await request<Directions>(`routes/${encodeURIComponent(routeId)}`, signal);
  const matches = detail.variants.filter(v => v.id && arrival.headsign && normalized(v.headsign) === normalized(arrival.headsign));
  if (matches.length === 1) return { pathname: '/line/[id]/[variant]', params: { id: routeId, variant: matches[0].id! } };
  return { pathname: '/line/[id]', params: { id: routeId } };
}
