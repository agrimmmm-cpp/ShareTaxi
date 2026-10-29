import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { Pressable, View } from 'react-native';

import { useMyRequests, usePopularRoutes, useQuote, useRides } from '@/api/hooks';
import { RideRequest } from '@/api/types';
import { SavingsRow } from '@/components/cards';
import { DateTimeField, PlaceInput } from '@/components/inputs';
import { Badge, Button, Card, Divider, Empty, Row, Screen, Section, Spacer, Text } from '@/components/ui';
import { ModeToggle } from '@/components/ModeToggle';
import { dayLabel, timeLabel } from '@/lib/format';
import { useAuth } from '@/store/auth';
import { useDraft } from '@/store/draft';
import { colors, radius, shadow, space } from '@/theme';

const POOL = ['searching', 'group_found', 'driver_search', 'driver_found'];

export default function Home() {
  const router = useRouter();
  const me = useAuth((s) => s.me);
  const d = useDraft();
  const rides = useRides('passenger');
  const requests = useMyRequests();
  const popular = usePopularRoutes();
  const quote = useQuote(d.origin, d.destination);

  const upcoming = (rides.data ?? []).filter((r) => ['confirmed', 'driver_arriving', 'active'].includes(r.status)).sort((a, b) => a.scheduled_departure.localeCompare(b.scheduled_departure))[0];
  const searching = (requests.data ?? []).filter((r) => POOL.includes(r.status));
  const ready = d.origin.trim().length > 1 && d.destination.trim().length > 1;

  return (
    <Screen>
      <Row style={{ justifyContent: 'space-between', marginBottom: space.lg }}>
        <View>
          <Text color={colors.mute}>Hi {me?.full_name.split(' ')[0]} 👋</Text>
          <Text variant="title">Where are you going?</Text>
        </View>
        <Pressable onPress={() => router.push('/notifications')} style={{ padding: 8 }}><Ionicons name="notifications-outline" size={24} color={colors.ink} /></Pressable>
      </Row>
      <ModeToggle />
      <Spacer h={space.md} />

      <View style={{ backgroundColor: colors.card, borderRadius: radius.xl, padding: space.lg, gap: space.md, ...shadow.float }}>
        <PlaceInput value={d.origin} onChange={(v) => d.set({ origin: v })} placeholder="Pickup" icon="radio-button-on" />
        <PlaceInput value={d.destination} onChange={(v) => d.set({ destination: v })} placeholder="Destination" icon="square" tint={colors.ink} />
        <DateTimeField value={d.departure} onChange={(v) => d.set({ departure: v })} />
        {quote.data && ready && <SavingsRow solo={quote.data.solo_benchmark} shared={quote.data.typical_shared_fare} compact />}
        <Button title="Find Shared Ride" icon="search" disabled={!ready} onPress={() => router.push('/(passenger)/explore')} />
        <Row>
          <Button title="Post Ride Request" variant="soft" icon="add-circle-outline" disabled={!ready} onPress={() => router.push('/request/new')} style={{ flex: 1 }} small />
          <Button title="Drive & Earn" variant="secondary" icon="car-sport-outline" small style={{ flex: 1 }}
            onPress={() => router.push(me?.roles.includes('driver') ? '/driver/new-trip' : '/driver/apply')} />
        </Row>
      </View>

      <Section title="Upcoming ride">
        {upcoming ? (
          <Card onPress={() => router.push(`/ride/${upcoming.id}`)}>
            <Row style={{ justifyContent: 'space-between' }}>
              <Text variant="h2" style={{ flex: 1 }} numberOfLines={1}>{upcoming.headline}</Text>
              <Badge label={upcoming.status.replace('_', ' ')} tone="savings" />
            </Row>
            <Text color={colors.inkSoft} style={{ marginTop: 4 }}>{dayLabel(upcoming.scheduled_departure)} · {timeLabel(upcoming.your_pickup_eta ?? upcoming.scheduled_departure)} pickup</Text>
            <Text color={colors.mute} variant="caption">{upcoming.driver.name} · {upcoming.driver.vehicle.color} {upcoming.driver.vehicle.make} · {upcoming.driver.vehicle.license_plate}</Text>
          </Card>
        ) : <Card><Text color={colors.mute}>No upcoming rides yet. Post a trip and we'll find people going your way.</Text></Card>}
      </Section>

      <Section title="Potential matches" action={searching.length ? { label: 'See all', onPress: () => router.push('/(passenger)/rides') } : undefined}>
        {searching.length ? <View style={{ gap: space.md }}>{searching.slice(0, 3).map((r) => <RequestRow key={r.id} r={r} onPress={() => router.push(`/request/${r.id}`)} />)}</View>
          : <Card><Text color={colors.mute}>Nothing pending. Your matches show up here as riders join.</Text></Card>}
      </Section>

      <Section title="Popular routes">
        {popular.data?.length ? (
          <View style={{ gap: space.sm }}>
            {popular.data.map((p) => (
              <Card key={`${p.origin}-${p.destination}`} onPress={() => d.set({ origin: p.origin, destination: p.destination })} style={{ paddingVertical: space.md }}>
                <Row style={{ justifyContent: 'space-between' }}>
                  <View style={{ flex: 1 }}><Text variant="bodyBold">{p.origin} → {p.destination}</Text><Text variant="caption" color={colors.mute}>{Math.round(p.distance_km)} km · {p.requests} riders posted</Text></View>
                  <View style={{ alignItems: 'flex-end' }}><Text variant="h2" color={colors.savings}>~${Math.round(p.typical_shared_fare)}</Text><Text variant="caption" color={colors.mute} style={{ textDecorationLine: 'line-through' }}>${Math.round(p.typical_solo_benchmark)}</Text></View>
                </Row>
              </Card>
            ))}
          </View>
        ) : <Empty icon="trending-up" title="Routes appear as riders post trips" />}
      </Section>
      <Divider />
      <Text variant="caption" color={colors.mute}>Solo prices shown are a configurable estimate, not a quote from any ride-hailing company.</Text>
    </Screen>
  );
}

export function RequestRow({ r, onPress }: { r: RideRequest; onPress: () => void }) {
  const tone = r.status === 'driver_found' ? 'savings' : r.status === 'searching' ? 'neutral' : 'info';
  return (
    <Card onPress={onPress} style={{ paddingVertical: space.md }}>
      <Row style={{ justifyContent: 'space-between' }}>
        <View style={{ flex: 1 }}>
          <Text variant="bodyBold" numberOfLines={1}>{r.origin_address} → {r.destination_address}</Text>
          <Text variant="caption" color={colors.mute}>{dayLabel(r.preferred_departure)} {timeLabel(r.preferred_departure)}</Text>
        </View>
        <Badge label={r.status.replace('_', ' ')} tone={tone} />
      </Row>
    </Card>
  );
}
