import { useRouter } from 'expo-router';
import { useState } from 'react';
import { View } from 'react-native';

import { useMyRequests, useRides } from '@/api/hooks';
import { Badge, Card, Chip, Empty, Loading, Row, Screen, Spacer, Text } from '@/components/ui';
import { dayLabel, money2, timeLabel } from '@/lib/format';
import { colors, space } from '@/theme';

import { RequestRow } from './index';

export default function MyRides() {
  const router = useRouter();
  const [tab, setTab] = useState<'upcoming' | 'past'>('upcoming');
  const rides = useRides('passenger');
  const reqs = useMyRequests();
  if (rides.isLoading || reqs.isLoading) return <Screen><Loading /></Screen>;
  const live = ['confirmed', 'driver_arriving', 'active'];
  const pool = ['searching', 'group_found', 'driver_search', 'driver_found'];
  const upcomingRides = (rides.data ?? []).filter((r) => live.includes(r.status));
  const pastRides = (rides.data ?? []).filter((r) => !live.includes(r.status));
  const waiting = (reqs.data ?? []).filter((r) => pool.includes(r.status));
  const pastReqs = (reqs.data ?? []).filter((r) => ['cancelled', 'expired'].includes(r.status));
  const showUpcoming = tab === 'upcoming';
  return (
    <Screen>
      <Text variant="title">My Rides</Text>
      <Row style={{ marginVertical: space.lg }}><Chip label="Upcoming" selected={showUpcoming} onPress={() => setTab('upcoming')} /><Chip label="Past" selected={!showUpcoming} onPress={() => setTab('past')} /></Row>
      <View style={{ gap: space.md }}>
        {showUpcoming && waiting.map((r) => <RequestRow key={`q${r.id}`} r={r} onPress={() => router.push(`/request/${r.id}`)} />)}
        {(showUpcoming ? upcomingRides : pastRides).map((r) => (
          <Card key={r.id} onPress={() => router.push(`/ride/${r.id}`)}>
            <Row style={{ justifyContent: 'space-between' }}>
              <Text variant="h2" style={{ flex: 1 }} numberOfLines={1}>{r.headline}</Text>
              <Badge label={r.status.replace('_', ' ')} tone={r.status === 'cancelled' ? 'danger' : r.status === 'completed' ? 'neutral' : 'savings'} />
            </Row>
            <Text color={colors.inkSoft}>{dayLabel(r.scheduled_departure)} {timeLabel(r.scheduled_departure)} · {r.passenger_count} riders</Text>
            {r.your_fare && <Text variant="bodyBold" style={{ marginTop: 4 }}>{money2(r.your_fare.fare)} <Text variant="caption" color={colors.savings}>saved {money2(r.your_fare.savings)}</Text></Text>}
          </Card>
        ))}
        {!showUpcoming && pastReqs.map((r) => <RequestRow key={`p${r.id}`} r={r} onPress={() => router.push(`/request/${r.id}`)} />)}
      </View>
      {((showUpcoming && !waiting.length && !upcomingRides.length) || (!showUpcoming && !pastRides.length && !pastReqs.length)) && (
        <Empty icon="car-outline" title={showUpcoming ? 'No upcoming rides' : 'No past rides'} body="Post a trip from Home and we'll find people heading your way." />
      )}
      <Spacer />
    </Screen>
  );
}
