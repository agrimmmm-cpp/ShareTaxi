import { Ionicons } from '@expo/vector-icons';
import { View } from 'react-native';

import type { ExploreCard, FareBreakdown, Match, RideGroup, RequestStatus, SearchSummary } from '@/api/types';
import { dayLabel, duration, money, money2, pct, timeLabel, windowLabel } from '@/lib/format';
import { colors, radius, space } from '@/theme';

import { Badge, Button, Card, Divider, Row, Text } from './ui';

/** "Uber-style estimated solo cost $90 · ShareTaxi $31 · You save $59 (65%)" — benchmark is configurable, not a real quote. */
export function SavingsRow({ solo, shared, compact }: { solo: number | null; shared: number | null; compact?: boolean }) {
  if (solo == null || shared == null) return null;
  const saved = solo - shared;
  const percent = solo > 0 ? (saved / solo) * 100 : 0;
  return (
    <View style={{ backgroundColor: colors.savingsSoft, borderRadius: radius.md, padding: space.md }}>
      <Row style={{ justifyContent: 'space-between' }}>
        <View>
          <Text variant="label" color={colors.mute}>Solo ride (est.)</Text>
          <Text variant="bodyBold" color={colors.mute} style={{ textDecorationLine: 'line-through' }}>{money(solo)}</Text>
        </View>
        <View>
          <Text variant="label" color={colors.savings}>Shared</Text>
          <Text variant={compact ? 'h2' : 'money'} color={colors.ink}>{money2(shared)}</Text>
        </View>
        <View style={{ alignItems: 'flex-end' }}>
          <Text variant="label" color={colors.savings}>You save</Text>
          <Text variant="h2" color={colors.savings}>{money(saved)}</Text>
          <Text variant="caption" color={colors.savings}>{pct(percent)} less</Text>
        </View>
      </Row>
    </View>
  );
}

const STAGES: { key: RequestStatus[]; label: string }[] = [
  { key: ['searching'], label: 'Searching for riders' },
  { key: ['group_found'], label: 'Potential group found' },
  { key: ['driver_search'], label: 'Driver search started' },
  { key: ['driver_found'], label: 'Driver found' },
  { key: ['confirmed'], label: 'Ride confirmed' },
  { key: ['driver_arriving'], label: 'Driver arriving' },
  { key: ['active'], label: 'Ride active' },
  { key: ['completed'], label: 'Completed' },
];

export function StatusTimeline({ status }: { status: RequestStatus }) {
  if (status === 'cancelled' || status === 'expired') return <Badge label={status === 'cancelled' ? 'Cancelled' : 'Expired'} tone="danger" />;
  const current = STAGES.findIndex((s) => s.key.includes(status));
  return (
    <View style={{ gap: 0 }}>
      {STAGES.map((s, i) => {
        const done = i < current, now = i === current;
        return (
          <Row key={s.label} gap={12} align="flex-start">
            <View style={{ alignItems: 'center', width: 20 }}>
              <View style={{ width: 14, height: 14, borderRadius: 7, marginTop: 3, backgroundColor: done || now ? colors.brand : colors.line, borderWidth: now ? 4 : 0, borderColor: colors.brandSoft }} />
              {i < STAGES.length - 1 && <View style={{ width: 2, height: 18, backgroundColor: done ? colors.brand : colors.line }} />}
            </View>
            <Text variant={now ? 'bodyBold' : 'body'} color={now ? colors.ink : done ? colors.inkSoft : colors.mute}>{s.label}</Text>
          </Row>
        );
      })}
    </View>
  );
}

export function SearchSummaryCard({ s, party }: { s: SearchSummary; party?: number }) {
  return (
    <Card>
      <Row style={{ justifyContent: 'space-between' }}>
        <Text variant="h2">{s.stage}</Text>
        <Badge label={`${s.potential_matches} potential match${s.potential_matches === 1 ? '' : 'es'}`} tone={s.potential_matches ? 'brand' : 'neutral'} icon="people" />
      </Row>
      <Divider />
      <Row style={{ justifyContent: 'space-between' }}>
        <Fact icon="people-outline" label="Riders likely" value={`${s.likely_passengers}`} />
        <Fact icon="time-outline" label="Trip time" value={duration(s.estimated_duration_min)} />
        <Fact icon="calendar-outline" label="Departing" value={windowLabel(s.departure_from, s.departure_to) || '–'} wide />
      </Row>
      <View style={{ height: space.md }} />
      {s.estimated_fare != null
        ? <SavingsRow solo={s.solo_benchmark} shared={s.estimated_fare} />
        : <Text color={colors.mute}>Solo ride would cost about {money(s.solo_benchmark)}. Share it and the price drops as riders join.</Text>}
      {s.fare_low != null && s.fare_high != null && <Text variant="caption" color={colors.mute} style={{ marginTop: 8 }}>Estimated fare {money2(s.fare_low)} – {money2(s.fare_high)}</Text>}
    </Card>
  );
}

function Fact({ icon, label, value, wide }: { icon: keyof typeof Ionicons.glyphMap; label: string; value: string; wide?: boolean }) {
  return (
    <View style={{ flex: wide ? 1.6 : 1 }}>
      <Row gap={4}><Ionicons name={icon} size={13} color={colors.mute} /><Text variant="caption" color={colors.mute}>{label}</Text></Row>
      <Text variant="bodyBold">{value}</Text>
    </View>
  );
}

/** Discovery card: "Vancouver → Abbotsford · Tomorrow 10:15 AM · 3 passengers · 1 seat remaining · fare · solo · save". */
export function GroupCard({ g, onPress, cta }: { g: RideGroup | ExploreCard; onPress?: () => void; cta?: { label: string; onPress: () => void; loading?: boolean } }) {
  const dev = 'pickup_deviation_min' in g ? g.pickup_deviation_min : null;
  return (
    <Card onPress={onPress}>
      <Row style={{ justifyContent: 'space-between' }}>
        <Text variant="h2" style={{ flex: 1 }} numberOfLines={1}>{g.headline}</Text>
        <Badge label={g.stage} tone={g.status === 'confirmed' ? 'savings' : 'info'} />
      </Row>
      <Text color={colors.inkSoft} style={{ marginTop: 4 }}>{dayLabel(g.suggested_departure)} {timeLabel(g.suggested_departure)}</Text>
      <Row gap={8} style={{ marginTop: space.md, flexWrap: 'wrap' }}>
        <Badge label={`${g.seats_used} passenger${g.seats_used === 1 ? '' : 's'}`} icon="people" tone="brand" />
        <Badge label={g.seats_left > 0 ? `${g.seats_left} seat${g.seats_left === 1 ? '' : 's'} left` : 'Full'} tone={g.seats_left > 0 ? 'neutral' : 'warn'} />
        {dev != null && <Badge label={`Pickup deviation ${Math.round(dev)} min`} icon="swap-horizontal" />}
      </Row>
      <View style={{ height: space.md }} />
      <SavingsRow solo={g.solo_benchmark} shared={g.your_fare ?? g.fare_high} compact />
      {cta && <Button title={cta.label} onPress={cta.onPress} loading={cta.loading} style={{ marginTop: space.md }} />}
    </Card>
  );
}

export function FareBreakdownCard({ f }: { f: FareBreakdown }) {
  const rows: [string, number][] = [['Distance travelled', f.distance_part], ['Time in vehicle', f.time_part], ['Detour contribution', f.detour_part]];
  return (
    <Card>
      <Text variant="h2">Your fare, explained</Text>
      <Text variant="caption" color={colors.mute} style={{ marginBottom: space.sm }}>Split by how far and how long you ride — not equally.</Text>
      {rows.map(([l, v]) => (
        <Row key={l} style={{ justifyContent: 'space-between', paddingVertical: 4 }}><Text color={colors.inkSoft}>{l}</Text><Text>{money2(v)}</Text></Row>
      ))}
      <Divider />
      <Row style={{ justifyContent: 'space-between' }}><Text variant="bodyBold">Total</Text><Text variant="bodyBold">{money2(f.fare)}</Text></Row>
      <Text variant="caption" color={colors.mute}>Includes {money2(f.platform_fee)} service fee</Text>
      <View style={{ height: space.md }} />
      <SavingsRow solo={f.solo_benchmark} shared={f.fare} compact />
    </Card>
  );
}

/** Driver-side recommendation: who, where, how much extra driving, what you earn. */
export function MatchCard({ m, selected, onSelect, onAccept, onReject, busy }: {
  m: Match; selected?: boolean; onSelect: () => void; onAccept: () => void; onReject: () => void; busy?: boolean;
}) {
  const areas = m.stops.filter((s) => s.kind === 'pickup').map((s) => s.area);
  const drops = m.stops.filter((s) => s.kind === 'dropoff').map((s) => s.area);
  return (
    <Card onPress={onSelect} style={selected ? { borderWidth: 2, borderColor: colors.driver } : undefined}>
      <Row style={{ justifyContent: 'space-between' }}>
        <Row gap={8}><Badge label={`${m.passengers} passenger${m.passengers === 1 ? '' : 's'}`} icon="people" tone="driver" /><Badge label={`Match ${Math.round(m.overall_score)}`} tone="savings" /></Row>
        <View style={{ alignItems: 'flex-end' }}>
          <Text variant="money" color={colors.driver}>{money(m.driver_net_earnings)}</Text>
          <Text variant="caption" color={colors.mute}>you earn after costs</Text>
        </View>
      </Row>
      <Divider />
      <Row gap={8} align="flex-start"><Ionicons name="ellipse" size={10} color={colors.brand} style={{ marginTop: 6 }} /><Text style={{ flex: 1 }}>Pick up: {areas.join(' → ')}</Text></Row>
      <Row gap={8} align="flex-start"><Ionicons name="square" size={10} color={colors.ink} style={{ marginTop: 6 }} /><Text style={{ flex: 1 }}>Drop off: {drops.join(' → ')}</Text></Row>
      <Row style={{ justifyContent: 'space-between', marginTop: space.md }}>
        <Fact icon="add-circle-outline" label="Added" value={`${Math.round(m.added_min)} min`} />
        <Fact icon="speedometer-outline" label="Trip" value={`${Math.round(m.total_km)} km`} />
        <Fact icon="cash-outline" label="Fares" value={money2(m.total_fare)} />
        <Fact icon="receipt-outline" label="Payout" value={money2(m.driver_payout)} />
      </Row>
      {selected && (
        <View style={{ marginTop: space.md, gap: 4 }}>
          {m.cost_lines.map((l) => <Row key={l.label} style={{ justifyContent: 'space-between' }}><Text variant="caption" color={colors.mute}>{l.label}</Text><Text variant="caption">{money2(l.amount)}</Text></Row>)}
          <Row style={{ justifyContent: 'space-between' }}><Text variant="caption" color={colors.mute}>Platform fee</Text><Text variant="caption">−{money2(m.platform_fee)}</Text></Row>
          <Row style={{ justifyContent: 'space-between' }}><Text variant="caption" color={colors.mute}>Operating cost (fuel, wear)</Text><Text variant="caption">−{money2(m.operating_cost)}</Text></Row>
        </View>
      )}
      <Row style={{ marginTop: space.md }}>
        <Button title="Reject" variant="secondary" small onPress={onReject} disabled={busy} style={{ flex: 1 }} />
        <Button title="Accept group" variant="driver" small onPress={onAccept} loading={busy} style={{ flex: 2 }} />
      </Row>
    </Card>
  );
}
