import React from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { useTheme } from './Theme';
import { typography } from './design';

export function UpdateStatus({ timestamp, message }: { timestamp: number | null; message?: string }) {
  const { colors } = useTheme();
  const time = timestamp ? new Date(timestamp * 1000).toLocaleTimeString('it-IT', {
    timeZone: 'Europe/Rome', hour: '2-digit', minute: '2-digit', second: '2-digit',
  }) : null;
  return <View style={styles.container}>
    {time && <Text style={[styles.text, { color: colors.muted }]}>Aggiornato alle {time}</Text>}
    {!!message && <Text style={[styles.text, { color: colors.muted }]}>{message}</Text>}
  </View>;
}

const styles = StyleSheet.create({ container: { gap: 2 }, text: typography.caption });
