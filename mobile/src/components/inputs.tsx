import { Ionicons } from '@expo/vector-icons';
import { useMemo, useState } from 'react';
import { Pressable, TextInput, View } from 'react-native';

import { usePlaces } from '@/api/hooks';
import { dayLabel, startOfDay } from '@/lib/format';
import { colors, radius, space } from '@/theme';

import { Chip, Row, Text } from './ui';

/** Text input with suggestions from the known-places list. Free text is still allowed (the API geocodes it). */
export function PlaceInput({ value, onChange, placeholder, icon = 'location', tint = colors.brand }: {
  value: string; onChange: (v: string) => void; placeholder: string; icon?: keyof typeof Ionicons.glyphMap; tint?: string;
}) {
  const { data: places = [] } = usePlaces();
  const [focused, setFocused] = useState(false);
  const matches = useMemo(() => {
    const q = value.trim().toLowerCase();
    return places.filter((p) => p.name.toLowerCase().includes(q) && p.name.toLowerCase() !== q).slice(0, q ? 4 : 5);
  }, [places, value]);
  return (
    <View>
      <View style={{ flexDirection: 'row', alignItems: 'center', backgroundColor: colors.bg, borderRadius: radius.md, paddingHorizontal: space.md, minHeight: 52 }}>
        <Ionicons name={icon} size={20} color={tint} />
        <TextInput
          value={value} onChangeText={onChange} placeholder={placeholder} placeholderTextColor={colors.mute}
          onFocus={() => setFocused(true)} onBlur={() => setTimeout(() => setFocused(false), 150)}
          autoCorrect={false} style={{ flex: 1, paddingHorizontal: space.md, fontSize: 16, color: colors.ink }}
        />
        {value.length > 0 && <Pressable onPress={() => onChange('')} hitSlop={10}><Ionicons name="close-circle" size={18} color={colors.mute} /></Pressable>}
      </View>
      {focused && matches.length > 0 && (
        <View style={{ marginTop: 6, backgroundColor: colors.card, borderRadius: radius.md, borderWidth: 1, borderColor: colors.line, overflow: 'hidden' }}>
          {matches.map((p) => (
            <Pressable key={p.name} onPress={() => { onChange(p.name); setFocused(false); }} style={{ padding: space.md, flexDirection: 'row', alignItems: 'center', gap: 10 }}>
              <Ionicons name="location-outline" size={16} color={colors.mute} />
              <Text>{p.name}</Text>
            </Pressable>
          ))}
        </View>
      )}
    </View>
  );
}

const DAYS = 7;

/** Day chips + time stepper: a dependency-free date/time picker tuned for planned trips. */
export function DateTimeField({ value, onChange }: { value: Date; onChange: (d: Date) => void }) {
  const today = startOfDay(new Date());
  const days = Array.from({ length: DAYS }, (_, i) => new Date(today.getTime() + i * 86_400_000));
  const setDay = (d: Date) => { const n = new Date(d); n.setHours(value.getHours(), value.getMinutes(), 0, 0); onChange(n); };
  const shift = (min: number) => onChange(new Date(value.getTime() + min * 60_000));
  const label = value.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
  return (
    <View style={{ gap: space.md }}>
      <Row gap={8} style={{ flexWrap: 'wrap' }}>
        {days.map((d) => <Chip key={d.toISOString()} label={dayLabel(d)} selected={startOfDay(value).getTime() === d.getTime()} onPress={() => setDay(d)} />)}
      </Row>
      <Row style={{ justifyContent: 'space-between' }}>
        <Row gap={6}>
          <Chip label="−1h" onPress={() => shift(-60)} /><Chip label="−15" onPress={() => shift(-15)} />
        </Row>
        <Text variant="title">{label}</Text>
        <Row gap={6}>
          <Chip label="+15" onPress={() => shift(15)} /><Chip label="+1h" onPress={() => shift(60)} />
        </Row>
      </Row>
    </View>
  );
}

export function FlexibilityPicker({ value, onChange }: { value: number; onChange: (n: number) => void }) {
  return (
    <Row gap={8} style={{ flexWrap: 'wrap' }}>
      {[0, 15, 30, 60].map((m) => <Chip key={m} label={m === 0 ? 'Exact' : `±${m} min`} selected={value === m} onPress={() => onChange(m)} />)}
    </Row>
  );
}
