import React, { useMemo } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { useHomePreferences, type HomeContent } from '../lib/HomePreferences';
import { useTheme, type ThemeColors } from '../ui/Theme';
import { typography } from '../ui/design';

const options: { value: HomeContent; label: string }[] = [
  { value: 'recent-lines', label: 'Linee recenti' },
  { value: 'favorite-stops', label: 'Fermate preferite' },
];

export function HomeContentPicker() {
  const { colors } = useTheme();
  const s = useMemo(() => createStyles(colors), [colors]);
  const { content, setContent, storageError } = useHomePreferences();
  return <View style={s.picker}>
    <View accessibilityRole="radiogroup" accessibilityLabel="Contenuto della home" style={s.options}>
      {options.map(option => <Pressable key={option.value} accessibilityRole="radio" accessibilityLabel={option.label} aria-checked={content === option.value} accessibilityState={{ checked: content === option.value }} onPress={() => setContent(option.value)} style={({ pressed }) => [s.option, content === option.value && s.selected, pressed && s.pressed]}>
        <Text style={[s.text, content === option.value && s.selectedText]}>{option.label}</Text>
      </Pressable>)}
    </View>
    <Text style={s.description}>Scegli cosa mostrare in evidenza nella home. La scelta viene salvata su questo dispositivo.</Text>
    {!!storageError && <Text accessibilityRole="alert" style={s.description}>{storageError}</Text>}
  </View>;
}

const createStyles = (colors: ThemeColors) => StyleSheet.create({
  picker: { gap: 10 }, options: { flexDirection: 'row', gap: 4, padding: 4, borderRadius: 16, backgroundColor: colors.surfaceAlt, borderWidth: 1, borderColor: colors.border },
  option: { flex: 1, minHeight: 48, paddingHorizontal: 6, paddingVertical: 10, alignItems: 'center', justifyContent: 'center', borderRadius: 12 }, selected: { backgroundColor: colors.accentFill }, pressed: { opacity: 0.8 },
  text: { ...typography.label, color: colors.muted, textAlign: 'center' }, selectedText: { color: colors.onAccent, fontWeight: '800' }, description: { ...typography.caption, color: colors.muted },
});
