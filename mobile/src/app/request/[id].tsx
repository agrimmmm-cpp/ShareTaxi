import { Ionicons } from '@expo/vector-icons';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { View } from 'react-native';

import { useCancelRequest, useGroup, useRequest, useRequestMatches } from '@/api/hooks';
import { SavingsRow, SearchSummaryCard, StatusTimeline } from '@/components/cards';
import { MapRoute } from '@/components/MapRoute';
import { Badge, Button, Card, Divider, ErrorBanner, Loading, Row, Screen, Section, Text } from '@/components/ui';
import { dayLabel, money2, timeLabel, windowLabel } from '@/lib/format';
import { colors, space } from '@/theme';

export default function RequestDetail() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const rid = Number(id);
  const router = useRouter();
  const req = useRequest(rid);
  const r = req.data;
  const group = useGroup(r?.search?.group_id);
  const inPool = !!r && ['searching', 'group_found', 'driver_search', 'driver_found'].includes(r.status);
  const matches = useRequestMatches(rid, inPool && ['driver_found'].includes(r.status));
  const cancel = useCancelRequest();

  if (req.isLoading || !r) return <Screen><Loading /></Screen>;
  const g = group.data;
  const best = matches.data?.[0];

  return (
    <Screen footer={inPool ? <Button title="Cancel request (free)" variant="danger" loading={cancel.isPending} onPress={() => cancel.mutate(rid, { onSuccess: () => router.back() })} /> : r.ride_id ? <Button title="View ride" icon="car" onPress={() => router.replace(`/ride/${r.ride_id}`)} /> : undefined}>
      <Row style={{ justifyContent: 'space-between' }}>
        <Text variant="title" style={{ flex: 1 }} numberOfLines={2}>{r.origin_address} → {r.destination_address}</Text>
        <Text variant="bodyBold" color={colors.brand} onPress={() => router.back()}>Back</Text>
      </Row>
      <Text color={colors.inkSoft} style={{ marginVertical: space.sm }}>{dayLabel(r.preferred_departure)} · {timeLabel(r.preferred_departure)} (±{Math.round((new Date(r.latest_departure).getTime() - new Date(r.preferred_departure).getTime()) / 60000) || 0} min) · {r.passenger_count} rider{r.passenger_count > 1 ? 's' : ''}</Text>
      <ErrorBanner error={cancel.error} />
      <MapRoute height={190} lines={[{ id: 'r', encoded: r.route_polyline }]} markers={[
        { id: 'o', lat: r.origin_lat, lng: r.origin_lng, label: 'A' }, { id: 'd', lat: r.destination_lat, lng: r.destination_lng, label: 'B', kind: 'dropoff' }]} />

      {r.search && <View style={{ marginTop: space.lg }}><SearchSummaryCard s={r.search} /></View>}

      {g && inPool && (
        <Section title="Shared ride forming">
          <Card>
            <Text variant="bodyBold">{g.headline}</Text>
            <Text variant="caption" color={colors.mute}>Departing {windowLabel(g.window_start, g.window_end)}</Text>
            <Divider />
            {g.members.map((m) => (
              <Row key={m.label} style={{ justifyContent: 'space-between', paddingVertical: 5 }}>
                <Row gap={8}><Ionicons name="checkmark-circle" size={20} color={colors.savings} /><Text variant="bodyBold">{m.label}</Text></Row>
                <Text color={colors.mute}>{m.area}</Text>
              </Row>
            ))}
            {Array.from({ length: g.seats_left }).map((_, i) => (
              <Row key={`o${i}`} gap={8} style={{ paddingVertical: 5 }}><Ionicons name="ellipse-outline" size={20} color={colors.line} /><Text color={colors.mute}>Open seat</Text></Row>
            ))}
            <Divider />
            {r.status === 'driver_search' && <Row gap={8}><Ionicons name="search" size={16} color={colors.info} /><Text color={colors.info} variant="bodyBold">Finding a driver…</Text></Row>}
            {r.status === 'group_found' && <Text color={colors.mute}>We need {Math.max(0, 3 - g.seats_used)} more rider{3 - g.seats_used === 1 ? '' : 's'} before searching for a driver.</Text>}
            <Text variant="caption" color={colors.mute} style={{ marginTop: 6 }}>Your exact address stays private until the ride is confirmed.</Text>
          </Card>
        </Section>
      )}

      {r.status === 'driver_found' && best && (
        <Section title="Driver found">
          <Card tone="savings">
            <Text variant="bodyBold" color={colors.savings}>A driver can take your group. Waiting for them to accept.</Text>
            <Text style={{ marginTop: 6 }}>Your fare: <Text variant="bodyBold">{money2(best.your_fare)}</Text> · saves {money2(best.your_savings)} ({Math.round(best.your_savings_percent ?? 0)}%)</Text>
            <Text variant="caption" color={colors.mute}>Pickup around {timeLabel(best.stops.find((s) => s.label === 'You' && s.kind === 'pickup')?.eta ?? best.departure)} · {Math.round(best.added_min)} min added for the driver</Text>
          </Card>
        </Section>
      )}

      <Section title="Status"><Card><StatusTimeline status={r.status} /></Card></Section>
      {r.search?.estimated_fare != null && <View style={{ marginTop: space.lg }}><SavingsRow solo={r.search.solo_benchmark} shared={r.search.estimated_fare} /></View>}
      {r.status === 'confirmed' && <Badge label="Ride confirmed" tone="savings" />}
    </Screen>
  );
}
