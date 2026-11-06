import React, { useEffect, useState } from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { useLocalSearchParams } from 'expo-router';
import { Badge, Notice, RequestState, useData, type Route } from '../../App';
import type { Departure } from '../lib/departures';
import { GlassSurface } from '../ui/Glass';
import { useTheme } from '../ui/Theme';
import { layout, typography } from '../ui/design';
import { UpdateStatus } from '../ui/UpdateStatus';
import { DepartureTile } from './DepartureTile';

type Day = {
  route: Route;
  selectedVariant: { headsign: string; fromName: string };
  date: string;
  departures: Departure[];
  liveAvailable: boolean;
  timestamp: number | null;
};

export function DailyDepartures() {
  const { colors } = useTheme();
  const { id, variant } = useLocalSearchParams<{ id: string; variant: string }>();
  const state = useData<Day>(id && variant ? `routes/${encodeURIComponent(id)}/departures?variant=${encodeURIComponent(variant)}` : null, 10000, true);
  const [tick, setNow] = useState(() => Date.now() / 1000);
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now() / 1000), 10000);
    return () => clearInterval(timer);
  }, []);
  const now = Math.max(tick, state.receivedAt);
  const data = state.data;
  const date = data ? new Date(`${data.date}T12:00:00+01:00`).toLocaleDateString('it-IT', { timeZone: 'Europe/Rome', weekday: 'long', day: 'numeric', month: 'long' }) : '';
  return <View style={styles.page}>
    <Text accessibilityRole="header" style={[typography.title, { color: colors.text }]}>Partenze di oggi</Text>
    {!variant && <Notice text="Scegli una direzione della linea per vedere le partenze della giornata." />}
    <RequestState state={state} showLoading={!data} />
    {data && <>
      <GlassSurface style={styles.summary}>
        <View style={styles.row}><Badge name={data.route.name} /><View style={styles.details}>
          <Text style={[typography.label, { color: colors.text }]}>Verso {data.selectedVariant.headsign}</Text>
          <Text style={[typography.caption, { color: colors.muted }]}>Da {data.selectedVariant.fromName}</Text>
        </View></View>
        <Text style={[typography.caption, { color: colors.muted }]}>{date} · {data.departures.length} partenze</Text>
      </GlassSurface>
      <UpdateStatus timestamp={data.timestamp} message={!data.liveAvailable || state.error ? 'Previsioni live non disponibili · orari programmati' : undefined} />
      <Text style={[typography.caption, { color: colors.muted }]}>Tutte le partenze della giornata, in ordine di orario. «Program.» indica l’orario programmato.</Text>
      {!data.departures.length && <Notice text="Nessuna partenza prevista per oggi in questa direzione." />}
      <View style={styles.grid}>
        {data.departures.map(d => <DepartureTile key={`${d.tripId}-${d.serviceDate}`} departure={d} now={now} />)}
      </View>
    </>}
  </View>;
}

const styles = StyleSheet.create({
  page: { gap: layout.gap }, summary: { padding: layout.cardPadding, gap: 12 },
  row: { flexDirection: 'row', alignItems: 'center', gap: 12 }, details: { flex: 1, gap: 4 },
  grid: { flexDirection: 'row', flexWrap: 'wrap', gap: 10 },
});
