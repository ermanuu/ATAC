import React from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { clock } from '../../App';
import { departureLabel, departureState, type Departure } from '../lib/departures';
import { useTheme } from '../ui/Theme';
import { typography } from '../ui/design';
import { LiveIndicator } from '../ui/LiveIndicator';

export function DepartureTime({ departure, now }: { departure: Departure; now: number }) {
  const { colors } = useTheme();
  const status = departureState(departure, now);
  const highlighted = departure.kind === 'live' && status !== 'departed';
  const label = highlighted ? 'Live' : departureLabel(departure, now);
  const color = highlighted ? colors.live : status === 'departed' ? colors.muted : colors.text;
  return <View accessible accessibilityLabel={`Partenza ${clock(departure.time)}, ${label}, ${departure.kind === 'live' ? 'previsione live' : 'orario programmato'}`}
    style={styles.content}>
    <Text style={[styles.time, { color }]}>{clock(departure.time)}</Text>
    {highlighted ? <LiveIndicator /> : <Text numberOfLines={1} style={[styles.status, { color: colors.muted }]}>{label}</Text>}
  </View>;
}

export function DepartureTile(props: { departure: Departure; now: number }) {
  return <DepartureTime {...props} />;
}

const styles = StyleSheet.create({
  content: { minWidth: 64, alignItems: 'center', justifyContent: 'center', gap: 2, paddingVertical: 2 },
  time: typography.time,
  status: typography.caption,
});
