import React from 'react';
import { ScrollView, StyleSheet, Text, View } from 'react-native';
import { router, useLocalSearchParams } from 'expo-router';
import { Badge, Notice, RequestState, clock, useData, type Route } from '../../App';
import { groupScheduledDeparturesByDay, type Departure } from '../lib/departures';
import { GlassPressable, GlassSurface } from '../ui/Glass';
import { useTheme } from '../ui/Theme';
import { layout, typography } from '../ui/design';

type Timetable = {
  route: Route;
  selectedVariant: { headsign: string; fromName: string };
  date: string;
  nightService?: boolean;
  departures: Departure[];
};

const dateLabel = (date: string) => new Date(`${date}T12:00:00Z`).toLocaleDateString('it-IT', {
  timeZone: 'Europe/Rome', weekday: 'long', day: 'numeric', month: 'long',
});

export function DailyDepartures() {
  const { colors } = useTheme();
  const { id, variant, date, fromDirections } = useLocalSearchParams<{ id: string; variant: string; date?: string; fromDirections?: string }>();
  const state = useData<Timetable>(id && variant ? `routes/${encodeURIComponent(id)}/departures?variant=${encodeURIComponent(variant)}${date ? `&date=${encodeURIComponent(date)}` : ''}` : null, 0, true);
  const data = state.data;
  const changeDate = (offset: number) => {
    if (!data) return;
    const next = new Date(`${data.date}T12:00:00Z`);
    next.setUTCDate(next.getUTCDate()+offset);
    router.replace({ pathname: '/line/[id]/departures', params: { id, variant, date: next.toISOString().slice(0, 10), ...(fromDirections ? { fromDirections } : {}) } });
  };
  return <View style={styles.page}>
    <Text accessibilityRole="header" style={[typography.title, { color: colors.text }]}>Orari programmati</Text>
    {!variant && <Notice text="Scegli una direzione della linea per vedere gli orari." />}
    <RequestState state={state} showLoading={!data} />
    {data && <>
      <View style={styles.row}>
        <Badge name={data.route.name} /><View style={styles.details}>
          <Text style={[typography.label, { color: colors.text }]}>Da {data.selectedVariant.fromName}</Text>
          <Text style={[typography.caption, { color: colors.muted }]}>Verso {data.selectedVariant.headsign}</Text>
        </View>
      </View>
      <View style={styles.row}>
        <GlassPressable accessibilityRole="button" accessibilityLabel="Giorno precedente" disabled={state.loading} onPress={() => changeDate(-1)} style={styles.dateButton}>
          <Text style={[styles.arrow, { color: colors.accent }]}>‹</Text>
        </GlassPressable>
        <View style={styles.date}>
          <Text style={[typography.label, { color: colors.text, textAlign: 'center' }]}>{dateLabel(data.date)}</Text>
          <Text style={[typography.caption, { color: colors.muted }]}>{(data.nightService ?? data.route.name.toLowerCase().startsWith('n')) ? '23:00–06:00' : '04:00–03:59'}</Text>
        </View>
        <GlassPressable accessibilityRole="button" accessibilityLabel="Giorno successivo" disabled={state.loading} onPress={() => changeDate(1)} style={styles.dateButton}>
          <Text style={[styles.arrow, { color: colors.accent }]}>›</Text>
        </GlassPressable>
      </View>
      {!data.departures.length && <Notice text="Nessuna partenza programmata per la giornata selezionata." />}
      {groupScheduledDeparturesByDay(data.departures).map(section => <View key={section.date} style={styles.day}>
        {section.date !== data.date && <View style={styles.dayHeading}>
          <Text accessibilityRole="header" style={[typography.heading, { color: colors.text }]}>Dopo mezzanotte</Text>
          <Text style={[typography.caption, { color: colors.muted }]}>{dateLabel(section.date)} · giorno successivo</Text>
        </View>}
        <GlassSurface style={styles.timetable}>
          <View style={[styles.hourRow, styles.tableHeader, { borderColor: colors.border }]}>
            <Text style={[typography.caption, styles.hour, { color: colors.muted }]}>Ora</Text>
            <Text style={[typography.caption, { color: colors.muted }]}>Partenze</Text>
          </View>
          {section.hours.map((group, index) => <View key={group.hour} style={[styles.hourRow, index > 0 && { borderTopWidth: 1, borderColor: colors.border }]}>
            <Text accessibilityLabel={`Ore ${group.hour}`} style={[typography.heading, styles.hour, { color: colors.text }]}>{group.hour}</Text>
            <ScrollView horizontal showsHorizontalScrollIndicator accessibilityLabel={`Partenze delle ore ${group.hour} del ${section.date}`} style={styles.hourScroller} contentContainerStyle={styles.hourTrack}>
              {group.departures.map(d => <Text key={`${d.tripId}-${d.serviceDate}`} accessibilityLabel={`Partenza programmata ${clock(d.scheduledTime)}`} style={[styles.time, { color: colors.text }]}>{clock(d.scheduledTime)}</Text>)}
            </ScrollView>
          </View>)}
        </GlassSurface>
      </View>)}
    </>}
  </View>;
}

const styles = StyleSheet.create({
  page: { gap: layout.gap }, row: { flexDirection: 'row', alignItems: 'center', gap: 12 }, details: { flex: 1, gap: 4 },
  date: { flex: 1, alignItems: 'center', gap: 4 }, dateButton: { width: 44, height: 44, alignItems: 'center', justifyContent: 'center', borderRadius: 14 }, arrow: { fontSize: 28 },
  day: { gap: 10 }, dayHeading: { gap: 4 }, timetable: { overflow: 'hidden' }, tableHeader: { borderBottomWidth: 1, minHeight: 40 },
  hourRow: { flexDirection: 'row', alignItems: 'center', gap: 12, paddingHorizontal: 12, paddingVertical: 10, minHeight: 48 },
  hour: { width: 36, flexShrink: 0 }, hourScroller: { flex: 1, minWidth: 0 }, hourTrack: { gap: 16, paddingVertical: 2, alignItems: 'center' },
  time: { ...typography.body, fontWeight: '700', fontVariant: ['tabular-nums'] },
});
