import { useLocalSearchParams, useRouter } from 'expo-router';
import { useState } from 'react';
import { Alert, View } from 'react-native';

import { useDriverTrip, useMatchAction, usePatchTrip, useTripMatches } from '@/api/hooks';
import { MatchCard } from '@/components/cards';
import { MapRoute } from '@/components/MapRoute';
import { Badge, Button, Card, Empty, ErrorBanner, Loading, Row, Screen, Section, Stepper, Text } from '@/components/ui';
import { dayLabel, duration, timeLabel } from '@/lib/format';
import { colors, space } from '@/theme';

export default function TripDetail() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const tripId = Number(id);
  const router = useRouter();
  const trip = useDriverTrip(tripId);
  const matches = useTripMatches(tripId);
  const act = useMatchAction();
  const patch = usePatchTrip(tripId);
  const [sel, setSel] = useState<number | null>(null);
  const t = trip.data;
  if (!t) return <Screen><Loading /></Screen>;
  const list = matches.data ?? [];
  const chosen = list.find((m) => m.id === (sel ?? list[0]?.id));

  const accept = (mid: number) => act.mutate({ id: mid, action: 'accept' }, { onSuccess: (ride) => ride && router.replace(`/ride/${ride.id}`) });

  return (
    <Screen bg="#F4F3FC">
      <Row style={{ justifyContent: 'space-between' }}>
        <Text variant="title" style={{ flex: 1 }} numberOfLines={2}>{t.origin_address} → {t.destination_address}</Text>
        <Text variant="bodyBold" color={colors.driver} onPress={() => router.back()}>Back</Text>
      </Row>
      <Row gap={8} style={{ marginVertical: space.sm }}>
        <Badge label={t.status} tone={t.status === 'cancelled' ? 'danger' : 'driver'} />
        <Text color={colors.inkSoft}>{dayLabel(t.departure_time)} {timeLabel(t.departure_time)} · {duration(t.estimated_duration)} · {Math.round(t.estimated_distance)} km</Text>
      </Row>
      <ErrorBanner error={act.error ?? patch.error} />

      <MapRoute height={260}
        lines={[
          { id: 'direct', encoded: t.route_polyline, color: colors.mute, dashed: true, width: 4 },
          ...(chosen ? [{ id: 'shared', encoded: chosen.route_polyline, color: colors.driver, width: 6 }] : []),
        ]}
        markers={[
          { id: 'start', lat: t.origin_lat, lng: t.origin_lng, label: 'D', kind: 'driver' },
          ...(chosen?.stops ?? []).map((s) => ({ id: `s${s.order}`, lat: s.lat, lng: s.lng, label: String(s.order), kind: s.kind })),
          { id: 'end', lat: t.destination_lat, lng: t.destination_lng, label: '⚑', kind: 'dropoff' as const },
        ]} />
      {chosen && (
        <Card style={{ marginTop: space.md }}>
          <Text variant="label" color={colors.mute}>Direct vs shared route</Text>
          <Text>Direct {duration(t.estimated_duration)} → shared {duration(chosen.total_min)} (<Text variant="bodyBold" color={colors.driver}>+{Math.round(chosen.added_min)} min</Text>, +{Math.round(chosen.added_km)} km)</Text>
          {chosen.stops.map((s) => <Text key={s.order} variant="caption" color={colors.inkSoft}>{s.order}. {s.kind === 'pickup' ? 'Pick up' : 'Drop off'} {s.label} · {s.area}{s.eta ? ` · ${timeLabel(s.eta)}` : ''}</Text>)}
        </Card>
      )}

      {t.status === 'open' && (
        <>
          <Section title="Recommended passenger groups">
            {matches.isLoading ? <Loading /> : list.length === 0 ? (
              <Empty icon="people-outline" title="No matching passengers yet" body="We'll notify you when riders heading your way post. Try more seats, a longer detour, or a lower minimum." />
            ) : <View style={{ gap: space.md }}>{list.map((m) => (
              <MatchCard key={m.id} m={m} selected={chosen?.id === m.id} onSelect={() => setSel(m.id)} busy={act.isPending}
                onAccept={() => accept(m.id)} onReject={() => act.mutate({ id: m.id, action: 'reject' })} />
            ))}</View>}
          </Section>
          <Section title="Flexibility">
            <Card style={{ gap: space.lg }}>
              <Row style={{ justifyContent: 'space-between' }}><Text variant="bodyBold">Seats</Text><Stepper value={t.available_seats} min={1} max={7} onChange={(v) => patch.mutate({ available_seats: v })} /></Row>
              <Row style={{ justifyContent: 'space-between' }}><Text variant="bodyBold">Max detour</Text><Stepper value={t.maximum_detour_minutes} min={5} max={60} step={5} format={(v) => `${v} min`} onChange={(v) => patch.mutate({ maximum_detour_minutes: v })} /></Row>
              <Row style={{ justifyContent: 'space-between' }}><Text variant="bodyBold">Min earnings</Text><Stepper value={t.minimum_earnings} min={0} max={500} step={5} format={(v) => `$${v}`} onChange={(v) => patch.mutate({ minimum_earnings: v })} /></Row>
            </Card>
            <Button title="Cancel trip" variant="danger" small style={{ marginTop: space.md }} onPress={() => Alert.alert('Cancel this trip?', 'Nobody is booked yet, so there is no penalty.', [{ text: 'Keep', style: 'cancel' }, { text: 'Cancel trip', style: 'destructive', onPress: () => patch.mutate({ status: 'cancelled' }, { onSuccess: () => router.back() }) }])} />
          </Section>
        </>
      )}
      {t.ride_id && <Button title="Open confirmed ride" variant="driver" style={{ marginTop: space.lg }} onPress={() => router.push(`/ride/${t.ride_id}`)} />}
    </Screen>
  );
}
