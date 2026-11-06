import React from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { clock } from '../../App';
import { departureLabel, departureState, type Departure } from '../lib/departures';
import { useTheme } from '../ui/Theme';
import { typography } from '../ui/design';
import { LiveIndicator } from '../ui/LiveIndicator';

export function DepartureTime({ departure, now, boxed = false }: { departure: Departure; now: number; boxed?: boolean }) {
  const { colors } = useTheme();
  const status = departureState(departure, now);
  const highlighted = departure.kind === 'live' && status !== 'departed';
  const label = boxed && highlighted ? 'Live' : departureLabel(departure, now);
  const color = highlighted ? colors.live : status === 'departed' ? colors.muted : colors.text;
  return <View accessible accessibilityLabel={`Partenza ${clock(departure.time)}, ${label}, ${departure.kind === 'live' ? 'previsione live' : 'orario programmato'}`}
    style={[styles.content, boxed && [styles.tile, { backgroundColor: status === 'terminal' && highlighted ? colors.liveSoft : colors.surfaceAlt, borderColor: status === 'terminal' && highlighted ? colors.live : colors.border }]]}>
    <Text style={[styles.time, { color }]}>{clock(departure.time)}</Text>
    {boxed && highlighted ? <LiveIndicator /> : <Text numberOfLines={1} style={[styles.status, { color: highlighted ? colors.live : colors.muted }]}>{label}</Text>}
  </View>;
}

export function DepartureTile(props: { departure: Departure; now: number }) {
  return <DepartureTime {...props} boxed />;
}

const styles = StyleSheet.create({
  content: { minWidth: 60, alignItems: 'center', justifyContent: 'center', gap: 2 },
  tile: { width: 60, height: 60, borderRadius: 12, borderWidth: 1 },
  time: { ...typography.body, fontWeight: '800', fontVariant: ['tabular-nums'] },
  status: typography.micro,
});
