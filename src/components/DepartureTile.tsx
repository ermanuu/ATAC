import React from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { clock } from '../../App';
import { departureState, type Departure } from '../lib/departures';
import { useTheme } from '../ui/Theme';
import { typography } from '../ui/design';

const labels = { terminal: 'Al capolinea', departed: 'Partito', live: 'Live', scheduled: 'Program.' };

export function DepartureTile({ departure, now }: { departure: Departure; now: number }) {
  const { colors } = useTheme();
  const status = departureState(departure, now);
  const highlighted = status === 'live' || status === 'terminal';
  const color = highlighted ? colors.live : status === 'departed' ? colors.muted : colors.text;
  return <View accessible accessibilityLabel={`Partenza ${clock(departure.time)}, ${labels[status]}, ${departure.kind === 'live' ? 'previsione live' : 'orario programmato'}`}
    style={[styles.tile, { backgroundColor: status === 'terminal' ? colors.liveSoft : colors.surfaceAlt, borderColor: status === 'terminal' ? colors.live : colors.border }]}>
    <Text style={[styles.time, { color }]}>{clock(departure.time)}</Text>
    <Text numberOfLines={1} style={[styles.status, { color: highlighted ? colors.live : colors.muted }]}>{labels[status]}</Text>
  </View>;
}

const styles = StyleSheet.create({
  tile: { width: 80, height: 80, borderRadius: 14, borderWidth: 1, alignItems: 'center', justifyContent: 'center', gap: 4 },
  time: typography.time,
  status: typography.micro,
});
