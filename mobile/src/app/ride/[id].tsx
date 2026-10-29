import { useLocalSearchParams, useRouter } from 'expo-router';
import { Alert, View } from 'react-native';

import { usePayments, useRide, useRideAction } from '@/api/hooks';
import { FareBreakdownCard, StatusTimeline } from '@/components/cards';
import { MapRoute } from '@/components/MapRoute';
import { Badge, Button, Card, Divider, ErrorBanner, Loading, Row, Screen, Section, Text } from '@/components/ui';
import { dayLabel, duration, money2, timeLabel } from '@/lib/format';
import { colors, space } from '@/theme';

const STATUS_MAP = { confirmed: 'confirmed', driver_arriving: 'driver_arriving', active: 'active', completed: 'completed', cancelled: 'cancelled' } as const;

export default function RideDetail() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const rid = Number(id);
  const router = useRouter();
  const ride = useRide(rid);
  const payments = usePayments();
  const act = useRideAction(rid);
  const r = ride.data;
  if (ride.isLoading || !r) return <Screen><Loading /></Screen>;

  const myPayment = payments.data?.find((p) => p.ride_id === rid);
  const needsPayment = !r.is_driver && ['confirmed', 'driver_arriving'].includes(r.status) && !(myPayment && ['authorized', 'captured'].includes(myPayment.status));
  const mine = r.stops.filter((s) => s.label === 'You' || r.is_driver);
  const confirmCancel = () =>
    Alert.alert('Cancel this ride?', r.is_driver ? 'Passengers will be re-matched with another driver. Your cancellation rate is tracked.' : 'A cancellation fee may apply depending on how close departure is.', [
      { text: 'Keep ride', style: 'cancel' },
      { text: 'Cancel ride', style: 'destructive', onPress: () => act.mutate({ action: 'cancel' }) },
    ]);

  const driverButton = r.is_driver && (
    r.status === 'confirmed' ? <Button title="I'm on my way" variant="driver" icon="navigate" loading={act.isPending} onPress={() => act.mutate({ action: 'arriving' })} />
    : r.status === 'driver_arriving' ? <Button title="Start ride" variant="driver" icon="play" loading={act.isPending} onPress={() => act.mutate({ action: 'start' })} />
    : r.status === 'active' ? <Button title="Complete ride" variant="driver" icon="checkmark-done" loading={act.isPending} onPress={() => act.mutate({ action: 'complete' })} /> : null
  );

  return (
    <Screen footer={driverButton || (needsPayment ? <Button title={`Add payment · ${money2(r.your_fare?.fare)}`} icon="card" onPress={() => router.push(`/pay/${rid}`)} /> : r.can_rate ? <Button title="Rate your ride" icon="star" onPress={() => router.push(`/rate/${rid}`)} /> : undefined)}>
      <Row style={{ justifyContent: 'space-between' }}>
        <Text variant="title" style={{ flex: 1 }} numberOfLines={2}>{r.headline}</Text>
        <Text variant="bodyBold" color={colors.brand} onPress={() => router.back()}>Back</Text>
      </Row>
      <Row gap={8} style={{ marginVertical: space.sm }}>
        <Badge label={r.status.replace('_', ' ')} tone={r.status === 'cancelled' ? 'danger' : 'savings'} />
        <Text color={colors.inkSoft}>{dayLabel(r.scheduled_departure)} {timeLabel(r.scheduled_departure)}</Text>
      </Row>
      <ErrorBanner error={act.error} />
      <MapRoute height={240} lines={[{ id: 'route', encoded: r.route_polyline }]}
        markers={mine.map((s) => ({ id: `${s.order}`, lat: s.lat, lng: s.lng, label: `${s.order}`, kind: s.kind, title: `${s.kind === 'pickup' ? 'Pick up' : 'Drop off'} ${s.label}` }))} />

      <Section title="Your driver">
        <Card>
          <Row gap={14}>
            <View style={{ width: 52, height: 52, borderRadius: 26, backgroundColor: colors.driverSoft, alignItems: 'center', justifyContent: 'center' }}><Text variant="h2" color={colors.driver}>{r.driver.name.slice(0, 1)}</Text></View>
            <View style={{ flex: 1 }}>
              <Text variant="h2">{r.driver.name}</Text>
              <Text color={colors.mute}>★ {r.driver.rating ? r.driver.rating.toFixed(1) : 'New'} · {r.driver.trips_completed} trips</Text>
            </View>
            <View style={{ alignItems: 'flex-end' }}>
              <Text variant="bodyBold">{r.driver.vehicle.license_plate}</Text>
              <Text variant="caption" color={colors.mute}>{r.driver.vehicle.color} {r.driver.vehicle.make} {r.driver.vehicle.model}</Text>
            </View>
          </Row>
        </Card>
      </Section>

      <Section title="Pickup & drop-off order">
        <Card>
          {r.stops.map((s, i) => (
            <View key={s.order}>
              {i > 0 && <Divider />}
              <Row gap={12}>
                <View style={{ width: 28, height: 28, borderRadius: s.kind === 'pickup' ? 14 : 8, backgroundColor: s.kind === 'pickup' ? colors.brand : colors.ink, alignItems: 'center', justifyContent: 'center' }}>
                  <Text variant="caption" color={colors.white} style={{ fontWeight: '800' }}>{s.order}</Text>
                </View>
                <View style={{ flex: 1 }}>
                  <Text variant="bodyBold">{s.kind === 'pickup' ? 'Pick up' : 'Drop off'} · {s.label}</Text>
                  <Text variant="caption" color={colors.mute}>{s.address ?? s.area}</Text>
                </View>
                {s.eta && <Text color={colors.inkSoft}>{timeLabel(s.eta)}</Text>}
              </Row>
            </View>
          ))}
          <Text variant="caption" color={colors.mute} style={{ marginTop: space.md }}>{duration(r.total_min)} · {Math.round(r.total_km)} km. Other riders only appear as neighbourhoods.</Text>
        </Card>
      </Section>

      <Section title={`Riders (${r.passenger_count})`}>
        <Card>
          {r.passengers.map((p, i) => (
            <View key={p.label}>{i > 0 && <Divider />}
              <Row style={{ justifyContent: 'space-between' }}><Text variant="bodyBold">{p.is_you ? 'You' : p.first_name ?? p.label}</Text><Text color={colors.mute}>{p.area}{p.rating ? ` · ★ ${p.rating.toFixed(1)}` : ''}</Text></Row>
            </View>
          ))}
        </Card>
      </Section>

      {r.your_fare && <View style={{ marginTop: space.lg }}><FareBreakdownCard f={r.your_fare} /></View>}
      {r.is_driver && r.driver_payout != null && (
        <Section title="Your earnings"><Card tone="driver"><Row style={{ justifyContent: 'space-between' }}><Text>Fares collected</Text><Text>{money2(r.total_fare)}</Text></Row><Row style={{ justifyContent: 'space-between' }}><Text variant="bodyBold">Your payout</Text><Text variant="bodyBold">{money2(r.driver_payout)}</Text></Row></Card></Section>
      )}

      <Section title="Progress"><Card><StatusTimeline status={STATUS_MAP[r.status] as never} /></Card></Section>

      <Section title="Stay connected">
        <Row>
          <Button title="Group chat" variant="secondary" icon="chatbubbles-outline" style={{ flex: 1 }} onPress={() => router.push(`/chat/${rid}`)} />
          <Button title="Safety" variant="secondary" icon="shield-checkmark-outline" style={{ flex: 1 }} onPress={() => router.push(`/safety/${rid}`)} />
        </Row>
        {['confirmed', 'driver_arriving'].includes(r.status) && <Button title="Cancel ride" variant="danger" small style={{ marginTop: space.md }} loading={act.isPending} onPress={confirmCancel} />}
      </Section>
    </Screen>
  );
}
