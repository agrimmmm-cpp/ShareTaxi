import { useRouter } from 'expo-router';
import { View } from 'react-native';

import { useDashboard } from '@/api/hooks';
import { ModeToggle } from '@/components/ModeToggle';
import { Badge, Button, Card, Empty, Loading, Row, Screen, Section, Text } from '@/components/ui';
import { dayLabel, money2, timeLabel, windowLabel } from '@/lib/format';
import { useAuth } from '@/store/auth';
import { colors, space } from '@/theme';

function Stat({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return <Card style={{ flex: 1, padding: space.md }}><Text variant="label" color={colors.mute}>{label}</Text><Text variant="title" color={tone ?? colors.ink}>{value}</Text></Card>;
}

export default function Dashboard() {
  const router = useRouter();
  const me = useAuth((s) => s.me);
  const q = useDashboard();
  const d = q.data;
  return (
    <Screen bg="#F4F3FC">
      <Text color={colors.mute}>Driver mode · {me?.full_name.split(' ')[0]}</Text>
      <Text variant="title" style={{ marginBottom: space.lg }}>Dashboard</Text>
      <ModeToggle />
      {!d ? <Loading /> : (
        <>
          <Row style={{ marginTop: space.lg }}><Stat label="Earned today" value={money2(d.earnings_today)} tone={colors.driver} /><Stat label="This week" value={money2(d.earnings_week)} /></Row>
          <Row style={{ marginTop: space.md }}><Stat label="Trips today" value={String(d.today_trips)} /><Stat label="Open seats" value={String(d.available_seats)} /><Stat label="Rating" value={d.rating_count ? d.rating.toFixed(1) : '–'} /></Row>
          <Button title="Post a trip" variant="driver" icon="add-circle" style={{ marginTop: space.lg }} onPress={() => router.push('/driver/new-trip')} />

          <Section title="Passenger requests nearby" action={{ label: 'View all', onPress: () => router.push('/(driver)/requests') }}>
            <Card tone="driver"><Text variant="h2" color={colors.driver}>{d.nearby_requests} riders</Text><Text color={colors.inkSoft}>are waiting for a ride on upcoming routes.</Text></Card>
          </Section>

          <Section title="Route demand">
            {d.route_demand.length ? <View style={{ gap: space.sm }}>{d.route_demand.map((c) => (
              <Card key={`${c.origin_area}${c.destination_area}${c.window_start}`} style={{ paddingVertical: space.md }}
                onPress={() => router.push('/(driver)/requests')}>
                <Row style={{ justifyContent: 'space-between' }}>
                  <View style={{ flex: 1 }}><Text variant="bodyBold">{c.origin_area} → {c.destination_area}</Text><Text variant="caption" color={colors.mute}>{windowLabel(c.window_start, c.window_end)}</Text></View>
                  <Badge label={`${c.passengers} looking`} tone={c.level === 'high' ? 'danger' : c.level === 'medium' ? 'warn' : 'neutral'} icon="people" />
                </Row>
              </Card>
            ))}</View> : <Empty icon="analytics-outline" title="No demand yet" />}
          </Section>

          <Section title="Upcoming trips" action={{ label: 'All trips', onPress: () => router.push('/(driver)/trips') }}>
            {d.upcoming_trips.length ? <View style={{ gap: space.sm }}>{d.upcoming_trips.map((t) => (
              <Card key={t.id} onPress={() => router.push(t.ride_id ? `/ride/${t.ride_id}` : `/driver/trip/${t.id}`)}>
                <Row style={{ justifyContent: 'space-between' }}><Text variant="bodyBold" style={{ flex: 1 }} numberOfLines={1}>{t.origin_address} → {t.destination_address}</Text><Badge label={t.status} tone={t.status === 'confirmed' ? 'savings' : 'driver'} /></Row>
                <Text color={colors.mute}>{dayLabel(t.departure_time)} {timeLabel(t.departure_time)} · {t.available_seats} seats{t.recommendations ? ` · ${t.recommendations} groups recommended` : ''}</Text>
              </Card>
            ))}</View> : <Card><Text color={colors.mute}>No trips posted. Post one and we'll match passengers.</Text></Card>}
          </Section>
          <Text variant="caption" color={colors.mute} style={{ marginTop: space.lg }}>Cancellation rate {(d.cancellation_rate * 100).toFixed(0)}% — riders see this, so cancel sparingly.</Text>
        </>
      )}
    </Screen>
  );
}
