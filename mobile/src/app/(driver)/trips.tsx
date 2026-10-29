import { useRouter } from 'expo-router';
import { View } from 'react-native';

import { useDriverTrips, useRides } from '@/api/hooks';
import { Badge, Button, Card, Empty, Loading, Row, Screen, Text } from '@/components/ui';
import { dayLabel, money2, timeLabel } from '@/lib/format';
import { colors, space } from '@/theme';

export default function Trips() {
  const router = useRouter();
  const trips = useDriverTrips();
  const rides = useRides('driver');
  return (
    <Screen bg="#F4F3FC">
      <Row style={{ justifyContent: 'space-between', marginBottom: space.lg }}>
        <Text variant="title">My Trips</Text>
        <Button title="Post" icon="add" variant="driver" small onPress={() => router.push('/driver/new-trip')} />
      </Row>
      {trips.isLoading ? <Loading /> : !trips.data?.length ? <Empty icon="map-outline" title="No trips yet" body="Post where you're driving and we'll recommend the best passenger groups." /> : (
        <View style={{ gap: space.md }}>
          {trips.data.map((t) => {
            const ride = rides.data?.find((r) => r.id === t.ride_id);
            return (
              <Card key={t.id} onPress={() => router.push(t.ride_id ? `/ride/${t.ride_id}` : `/driver/trip/${t.id}`)}>
                <Row style={{ justifyContent: 'space-between' }}>
                  <Text variant="h2" style={{ flex: 1 }} numberOfLines={1}>{t.origin_address} → {t.destination_address}</Text>
                  <Badge label={t.status} tone={t.status === 'cancelled' ? 'danger' : t.status === 'open' ? 'driver' : 'savings'} />
                </Row>
                <Text color={colors.inkSoft}>{dayLabel(t.departure_time)} {timeLabel(t.departure_time)} · {t.available_seats} seats · min {money2(t.minimum_earnings)}</Text>
                {t.status === 'open' && <Text variant="bodyBold" color={colors.driver}>{t.recommendations ?? 0} recommended group{t.recommendations === 1 ? '' : 's'}</Text>}
                {ride && <Text variant="bodyBold" color={colors.savings}>{ride.passenger_count} riders · payout {money2(ride.driver_payout)}</Text>}
              </Card>
            );
          })}
        </View>
      )}
    </Screen>
  );
}
