import type { TextStyle } from 'react-native';

export const typography = {
  title: { fontSize: 24, lineHeight: 30, fontWeight: '800' },
  heading: { fontSize: 20, lineHeight: 26, fontWeight: '700' },
  body: { fontSize: 16, lineHeight: 22 },
  label: { fontSize: 14, lineHeight: 20, fontWeight: '600' },
  caption: { fontSize: 12, lineHeight: 18 },
  micro: { fontSize: 11, lineHeight: 16 },
  time: { fontSize: 20, lineHeight: 26, fontWeight: '800', fontVariant: ['tabular-nums'] },
} satisfies Record<string, TextStyle>;

export const layout = { gutter: 20, gap: 16, cardPadding: 16, radius: 20, maxWidth: 640 };
