import React, { useMemo } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { useTheme, type ThemeColors, type ThemePreference } from '../ui/Theme';

const options: { value: ThemePreference; label: string }[] = [
  { value: 'system', label: 'Automatico' },
  { value: 'light', label: 'Chiaro' },
  { value: 'dark', label: 'Scuro' },
];

export function ThemePicker() {
  const { colors, preference, setPreference, storageError } = useTheme();
  const s = useMemo(() => createStyles(colors), [colors]);
  return <View style={s.picker}>
    <View accessibilityRole="radiogroup" accessibilityLabel="Aspetto dell’app" style={s.options}>
      {options.map(option => <Pressable key={option.value} accessibilityRole="radio" accessibilityLabel={`Tema: ${option.label}`} aria-checked={preference === option.value} accessibilityState={{ checked: preference === option.value }} onPress={() => setPreference(option.value)} style={({ pressed }) => [s.option, preference === option.value && s.selected, pressed && s.pressed]}>
        <Text style={[s.text, preference === option.value && s.selectedText]}>{option.label}</Text>
      </Pressable>)}
    </View>
    <Text style={s.description}>Automatico segue il tema del dispositivo. La scelta viene salvata su questo dispositivo.</Text>
    {!!storageError && <Text accessibilityRole="alert" style={s.description}>{storageError}</Text>}
  </View>;
}

const createStyles = (colors: ThemeColors) => StyleSheet.create({
  picker: { gap: 10 }, options: { flexDirection: 'row', gap: 4, padding: 4, borderRadius: 16, backgroundColor: colors.surfaceAlt, borderWidth: 1, borderColor: colors.border },
  option: { flex: 1, minHeight: 48, paddingHorizontal: 4, paddingVertical: 10, alignItems: 'center', justifyContent: 'center', borderRadius: 12 }, selected: { backgroundColor: colors.accentFill }, pressed: { opacity: 0.8 },
  text: { color: colors.muted, fontSize: 12, fontWeight: '600', textAlign: 'center' }, selectedText: { color: colors.onAccent, fontWeight: '800' }, description: { color: colors.muted, fontSize: 12, lineHeight: 18 },
});
