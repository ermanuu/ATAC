import React, { useEffect, useRef, useState } from 'react';
import { ActivityIndicator, AppState, Linking, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { StatusBar } from 'expo-status-bar';
import { Slot, router, usePathname } from 'expo-router';

const API = process.env.EXPO_PUBLIC_API_URL?.replace(/\/$/, '') || '';
type Stop = { stop_id: string; name: string };
type Route = { route_id: string; name: string; description: string };
type Live = { available: boolean; timestamp: number | null };
type Health = { staticAvailable: boolean; serviceToday?: boolean; vehicles: Live; updates: Live };
type Detail = { variants: { headsign: string; direction: string; stops: Stop[] }[]; vehicles: { id: string; lat: number; lon: number; timestamp: number; stopId: string; status: string }[]; liveAvailable: boolean; timestamp: number | null };
type Arrivals = { arrivals: { tripId: string; line: string; headsign: string; time: number; kind: string }[]; liveAvailable: boolean; timestamp: number | null };
type Journey = { message: string; legs: { line: string; fromName: string; toName: string; departure: number; arrival: number; stops: number }[] };
async function api<T>(path: string, signal?: AbortSignal): Promise<T> {
  if (!API) throw new Error('Configura EXPO_PUBLIC_API_URL con l’indirizzo del servizio dati raggiungibile dall’iPhone.');
  const response = await fetch(`${API}/api/${path}`, { signal });
  const body = await response.json();
  if (!response.ok) throw new Error(body.error || 'Servizio non disponibile');
  return body;
}
const clock = (t: number) => new Date(t * 1000).toLocaleTimeString('it-IT', { timeZone: 'Europe/Rome', hour: '2-digit', minute: '2-digit' });
const stamp = (t: number | null) => t ? `Aggiornato alle ${clock(t)}` : 'Nessun aggiornamento disponibile';
function Button({ text, onPress, disabled = false }: { text: string; onPress: () => void; disabled?: boolean }) {
  return <Pressable accessibilityRole="button" disabled={disabled} onPress={onPress} style={[s.button, disabled && { opacity: 0.4 }]}><Text style={s.buttonText}>{text}</Text></Pressable>;
}
function Notice({ text }: { text: string }) { return <View accessibilityRole="alert" style={s.notice}><Text style={s.muted}>{text}</Text></View>; }
function Badge({ name }: { name: string }) { return <View style={s.badge}><Text style={s.badgeText}>{name}</Text></View>; }

// Abort obsolete requests and clear live values during refresh: stale data never retains a live label.
function useData<T>(path: string | null, interval = 0) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    setData(null); setError(''); setLoading(false);
    if (!path) return;
    let controller: AbortController | undefined;
    const load = () => {
      controller?.abort(); controller = new AbortController(); const signal = controller.signal;
      setData(null); setError(''); setLoading(true);
      api<T>(path, signal).then(setData).catch(e => { if (!signal.aborted) setError(e.message); })
        .finally(() => { if (!signal.aborted) setLoading(false); });
    };
    const delay = setTimeout(load, 250);
    const timer = interval ? setInterval(load, interval) : undefined;
    const listener = AppState.addEventListener('change', state => { if (state === 'active') load(); });
    return () => { controller?.abort(); clearTimeout(delay); if (timer) clearInterval(timer); listener.remove(); };
  }, [path, interval, revision]);
  return { data, error, loading, retry: () => setRevision(n => n + 1) };
}
function RequestState({ state }: { state: { loading: boolean; error: string; retry: () => void } }) {
  return <>{state.loading && <ActivityIndicator color="#a01d35" />}{!!state.error && <><Notice text={state.error} /><Button text="Riprova" onPress={state.retry} /></>}</>;
}
function StopSearch({ label, selected, onSelect }: { label: string; selected: Stop | null; onSelect: (stop: Stop | null) => void }) {
  const [query, setQuery] = useState('');
  const state = useData<Stop[]>(!selected && query.trim().length >= 2 ? `stops?q=${encodeURIComponent(query.trim())}` : null);
  return <View><Text style={s.label}>{label}</Text>
    <TextInput accessibilityLabel={label} placeholder="Nome o codice fermata" placeholderTextColor="#738197" value={selected?.name || query} onChangeText={text => { onSelect(null); setQuery(text); }} style={s.input} autoCorrect={false} />
    <RequestState state={state} />
    {state.data?.length === 0 && <Text style={s.muted}>Nessuna fermata trovata.</Text>}
    {!selected && state.data?.map(stop => <Pressable accessibilityRole="button" key={stop.stop_id} style={s.stop} onPress={() => onSelect(stop)}><Text style={s.body}>{stop.name}</Text><Text style={s.small}>Fermata {stop.stop_id}</Text></Pressable>)}
  </View>;
}
export default function App() {
  const pathname = usePathname();
  const tab = pathname === '/stops' ? 'stops' : pathname === '/plan' ? 'plan' : 'lines';
  const state = useData<Health>('status', 30000);
  const live = state.data?.vehicles.available && state.data?.updates.available;
  return <SafeAreaView style={s.safe}><StatusBar style="dark" />
    <View style={s.header}><View style={s.row}><Text style={s.eyebrow}>ROMA · AUTOBUS</Text><Text style={[s.small, { color: live ? '#167450' : '#9b6a20' }]}>{live ? '● Feed live' : '● Live non disponibile'}</Text></View><Text style={s.title}>La città, in movimento.</Text><Text style={s.subtitle}>Linee, fermate e percorsi a Roma</Text></View>
    <View style={s.tabs}>{([['lines', 'Linee'], ['stops', 'Fermate'], ['plan', 'Percorso']] as const).map(([key, label]) => <Pressable accessibilityRole="tab" accessibilityState={{ selected: key === tab }} key={key} onPress={() => router.replace(key === 'lines' ? '/' : key === 'stops' ? '/stops' : '/plan')} style={[s.tab, key === tab && s.active]}><Text style={[s.tabText, key === tab && { color: '#a01d35' }]}>{label}</Text></Pressable>)}</View>
    <View style={s.content}><ScrollView keyboardShouldPersistTaps="handled" contentContainerStyle={s.scroll}>
      <RequestState state={state} />
      {state.data && !state.data.staticAvailable && <Notice text="Orari non ancora caricati. Il servizio deve importare il GTFS ufficiale Roma Mobilità." />}
      {state.data?.staticAvailable && !state.data.serviceToday && <Notice text="Il calendario importato non contiene servizio per oggi. Aggiornare il GTFS." />}
      <Slot />
    </ScrollView></View>
    <View style={s.footer}><Text style={s.small}>Dati: Roma Servizi per la Mobilità · App indipendente</Text><Text style={s.small}>{state.data?.updates.available ? stamp(state.data.updates.timestamp) : 'Le previsioni live possono essere indisponibili'}</Text></View>
  </SafeAreaView>;
}
export function Lines() {
  const [query, setQuery] = useState('');
  const [selected, setSelected] = useState<Route | null>(null);
  const state = useData<Route[]>(selected ? null : `routes?q=${encodeURIComponent(query)}`);
  const detail = useData<Detail>(selected ? `routes/${encodeURIComponent(selected.route_id)}` : null, 30000);
  if (selected) return <View style={s.stack}><Button text="‹ Tutte le linee" onPress={() => setSelected(null)} /><View style={s.row}><Badge name={selected.name} /><Text style={s.heading}>Percorso della linea</Text></View><RequestState state={detail} />
    {detail.data && <><Text style={s.heading}>Bus in servizio</Text><Text style={s.muted}>{detail.data.liveAvailable ? stamp(detail.data.timestamp) : 'Posizioni live non disponibili'}</Text>
      {detail.data.liveAvailable && !detail.data.vehicles.length && <Notice text="Nessun veicolo segnalato per questa linea. Non indica necessariamente assenza di servizio." />}
      {detail.data.vehicles.map(v => <View key={v.id} style={s.card}><Text style={s.body}>Bus {v.id}</Text><Text style={s.muted}>{v.status === 'STOPPED_AT' ? 'Fermo alla fermata' : v.status === 'INCOMING_AT' ? 'In avvicinamento' : 'In viaggio'} {v.stopId} · {clock(v.timestamp)}</Text><Pressable accessibilityRole="link" onPress={() => { void Linking.openURL(`https://maps.apple.com/?ll=${v.lat},${v.lon}&q=Bus%20${encodeURIComponent(selected.name)}`); }}><Text style={s.link}>Apri posizione in Mappe ↗</Text></Pressable></View>)}
      {!detail.data.variants.length && <Notice text="Nessun percorso programmato attivo oggi nel GTFS importato." />}
      {detail.data.variants.map((v,i) => <View key={i} style={s.card}><Text style={s.heading}>→ {v.headsign || `Direzione ${v.direction || i+1}`}</Text><Text style={s.muted}>Sequenza programmata · varianti e deviazioni live non incluse</Text>{v.stops.map((stop,j) => <View key={`${stop.stop_id}-${j}`} style={s.row}><Text style={s.link}>●</Text><View style={s.flex}><Text style={s.body}>{stop.name}</Text><Text style={s.small}>{stop.stop_id}</Text></View></View>)}</View>)}
    </>}
  </View>;
  return <View style={s.stack}><Text style={s.heading}>Trova il tuo autobus</Text><Text style={s.muted}>Cerca il numero o il nome della linea</Text><TextInput accessibilityLabel="Cerca linea autobus" value={query} onChangeText={setQuery} placeholder="Es. 64, 40, H…" placeholderTextColor="#738197" style={s.input} autoCorrect={false} /><RequestState state={state} />
    {state.data?.length === 0 && <Notice text="Nessuna linea trovata." />}
    {state.data?.map(r => <Pressable accessibilityRole="button" key={r.route_id} style={s.route} onPress={() => setSelected(r)}><Badge name={r.name} /><View style={s.flex}><Text style={s.body}>{r.description || `Linea ${r.name}`}</Text><Text style={s.small}>Percorso e posizioni live</Text></View><Text style={s.arrow}>›</Text></Pressable>)}
  </View>;
}
export function Stops() {
  const [stop, setStop] = useState<Stop | null>(null);
  const state = useData<Arrivals>(stop ? `stops/${encodeURIComponent(stop.stop_id)}/arrivals` : null, 30000);
  return <View style={s.stack}><Text style={s.heading}>Alla fermata</Text><Text style={s.muted}>Arrivi previsti e orari programmati</Text><StopSearch label="Fermata" selected={stop} onSelect={setStop} /><RequestState state={state} />
    {state.data && <><Text style={s.muted}>{state.data.liveAvailable ? stamp(state.data.timestamp) : 'Feed live non disponibile · solo orari programmati'}</Text>
      {!state.data.arrivals.length && <Notice text="Nessuna partenza nelle prossime 2 ore nel feed disponibile." />}
      {state.data.arrivals.map((a,i) => <View key={`${a.tripId}-${i}`} style={s.route}><Badge name={a.line} /><View style={s.flex}><Text style={s.body}>{a.headsign || 'Autobus'}</Text><Text style={[s.small, a.kind === 'live' && { color: '#167450' }]}>{a.kind === 'live' ? '● Previsione live' : 'Orario programmato'}</Text></View><Text style={s.time}>{clock(a.time)}</Text></View>)}
    </>}
  </View>;
}
export function Planner() {
  const [origin, setOrigin] = useState<Stop | null>(null);
  const [destination, setDestination] = useState<Stop | null>(null);
  const [journey, setJourney] = useState<Journey | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const request = useRef<AbortController | null>(null);
  useEffect(() => () => request.current?.abort(), []);
  const reset = () => { request.current?.abort(); setJourney(null); setError(''); setLoading(false); };
  const calculate = async () => {
    if (!origin || !destination) return;
    request.current?.abort(); const controller = new AbortController(); request.current = controller;
    setLoading(true); setJourney(null); setError('');
    try { setJourney(await api<Journey>(`plan?from=${encodeURIComponent(origin.stop_id)}&to=${encodeURIComponent(destination.stop_id)}`, controller.signal)); }
    catch (e) { if (!controller.signal.aborted) setError((e as Error).message); }
    finally { if (!controller.signal.aborted) setLoading(false); }
  };
  return <View style={s.stack}><Text style={s.heading}>Dove vuoi andare?</Text><Text style={s.muted}>Percorsi fra fermate, con partenza adesso</Text>
    <StopSearch label="Da" selected={origin} onSelect={v => { reset(); setOrigin(v); }} /><StopSearch label="A" selected={destination} onSelect={v => { reset(); setDestination(v); }} />
    <Button text={loading ? 'Calcolo in corso…' : 'Trova percorso →'} disabled={!origin || !destination || loading} onPress={() => { void calculate(); }} />
    <Notice text="Orari programmati: solo autobus, cambi alla stessa fermata e margine di 2 minuti. Nessun tratto a piedi; traffico e previsioni live non modificano l’itinerario." />
    {!!error && <Notice text={error} />}
    {journey && <><Text style={s.muted}>{journey.message}</Text>{journey.legs.map((leg,i) => <View key={i} style={s.card}><View style={s.row}><Badge name={leg.line} /><Text style={s.heading}>{clock(leg.departure)} → {clock(leg.arrival)}</Text></View><Text style={s.body}>{leg.fromName}</Text><Text style={s.muted}>↓ {leg.stops} {leg.stops === 1 ? 'fermata' : 'fermate'}</Text><Text style={s.body}>{leg.toName}</Text>{i < journey.legs.length-1 && <Text style={s.link}>Cambia autobus qui</Text>}</View>)}</>}
  </View>;
}
const s = StyleSheet.create({
  safe: { flex: 1, backgroundColor: '#f8f6f2' }, flex: { flex: 1 }, stack: { gap: 14 },
  header: { paddingHorizontal: 24, paddingTop: 20, paddingBottom: 24 }, row: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  eyebrow: { fontSize: 11, fontWeight: '800', color: '#a01d35', letterSpacing: 1.4, flex: 1 },
  title: { fontSize: 34, fontWeight: '800', color: '#202d3a', marginTop: 22, letterSpacing: -1.3 }, subtitle: { color: '#596878', fontSize: 16, marginTop: 8 },
  tabs: { flexDirection: 'row', marginHorizontal: 20, padding: 5, backgroundColor: '#ebe8e3', borderRadius: 16, marginBottom: 20 },
  tab: { flex: 1, paddingVertical: 12, alignItems: 'center', borderRadius: 12 }, active: { backgroundColor: '#fff' }, tabText: { fontWeight: '600', color: '#596878', fontSize: 15 },
  content: { flex: 1, paddingHorizontal: 20 }, scroll: { paddingBottom: 30, gap: 14 }, heading: { color: '#202d3a', fontSize: 20, fontWeight: '700', flexShrink: 1 },
  muted: { color: '#596878', fontSize: 14, lineHeight: 21 }, small: { color: '#596878', fontSize: 11, lineHeight: 16 }, body: { color: '#202d3a', fontSize: 16, fontWeight: '600' },
  input: { backgroundColor: '#fff', borderWidth: 1, borderColor: '#dedbd5', borderRadius: 14, paddingHorizontal: 16, paddingVertical: 16, color: '#202d3a', fontSize: 16, marginVertical: 12 },
  route: { paddingVertical: 18, borderBottomWidth: 1, borderBottomColor: '#e3dfd8', flexDirection: 'row', gap: 14, alignItems: 'center' },
  badge: { minWidth: 52, borderRadius: 12, padding: 12, backgroundColor: '#a01d35', alignItems: 'center' }, badgeText: { color: '#fff', fontSize: 18, fontWeight: '800' },
  arrow: { fontSize: 28, color: '#a01d35' }, time: { fontSize: 20, fontWeight: '700', color: '#202d3a' },
  button: { backgroundColor: '#a01d35', padding: 16, borderRadius: 14, alignItems: 'center' }, buttonText: { color: '#fff', fontWeight: '700', fontSize: 15 },
  notice: { backgroundColor: '#eee9df', padding: 14, borderRadius: 12, marginVertical: 8 }, card: { backgroundColor: '#fff', borderRadius: 18, padding: 18, gap: 12, borderColor: '#e4dfd8', borderWidth: 1 },
  label: { color: '#202d3a', fontSize: 13, fontWeight: '700' }, stop: { padding: 14, backgroundColor: '#fff', borderBottomWidth: 1, borderBottomColor: '#eee9df' },
  link: { color: '#a01d35', fontWeight: '600', fontSize: 14 }, footer: { padding: 12, alignItems: 'center', borderTopWidth: 1, borderColor: '#e3dfd8' },
});
