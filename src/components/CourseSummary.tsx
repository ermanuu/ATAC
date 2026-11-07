import React from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { useTheme } from '../ui/Theme';
import { typography } from '../ui/design';

type Course = { category?: string; headsign: string; fromName: string };

export function CourseSummary({ course, compact = false }: { course: Course; compact?: boolean }) {
  const { colors } = useTheme();
  return <View style={styles.details}>
    <Text style={[styles.category, { color: compact ? colors.muted : colors.accent }]}>{(course.category || 'Variante').toLocaleUpperCase('it-IT')}</Text>
    <Text style={[compact ? typography.body : typography.heading, { color: compact ? colors.muted : colors.text, fontWeight: '700' }]}>{course.headsign}</Text>
    <Text style={[typography.caption, { color: colors.muted }]}>DA {course.fromName}</Text>
  </View>;
}

const styles = StyleSheet.create({
  details: { flex: 1, minWidth: 0, gap: 4 },
  category: { ...typography.micro, fontWeight: '800', letterSpacing: 0.8 },
});
