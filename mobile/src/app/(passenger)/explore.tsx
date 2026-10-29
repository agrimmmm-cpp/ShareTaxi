import { useRouter } from 'expo-router';
import { View } from 'react-native';

import { useCreateRequest, useExplore, useJoinGroup } from '@/api/hooks';
import { GroupCard } from '@/components/cards';
import { DateTimeField, FlexibilityPicker, PlaceInput } from '@/components/inputs';
import { Button, Card, Empty, ErrorBanner, Loading, Screen, Section, Text } from '@/components/ui';
import { useDraft } from '@/store/draft';
import { colors, space } from '@/theme';

export default function Explore() {
  const router = useRouter();
  const d = useDraft();
  const ready = d.origin.trim().length > 1 && d.destination.trim().length > 1;
  const explore = useExplore(ready ? { origin: d.origin, destination: d.destination, departure: d.departure, flexible: d.flexibleMinutes, passengers: d.passengers } : null);
  const create = useCreateRequest();
  const join = useJoinGroup();
  const busy = create.isPending || join.isPending;

  // Passenger Mode: join a ride that is already forming. We post your request, then pin it to that group.
  const joinGroup = (groupId: number) =>
    create.mutate(
      { origin_address: d.origin, destination_address: d.destination, preferred_departure: d.departure.toISOString(), flexible_minutes: d.flexibleMinutes,
        passenger_count: d.passengers, luggage_count: 0, max_pickup_deviation_min: 10, maximum_detour_minutes: 25, ride_type: 'shared' },
      { onSuccess: (req) => join.mutate({ groupId, requestId: req.id }, { onSettled: () => router.push(`/request/${req.id}`) }) },
    );

  return (
    <Screen>
      <Text variant="title">Explore shared rides</Text>
      <Text color={colors.mute} style={{ marginBottom: space.lg }}>Rides already forming on your route</Text>
      <Card style={{ gap: space.md }}>
        <PlaceInput value={d.origin} onChange={(v) => d.set({ origin: v })} placeholder="Pickup" icon="radio-button-on" />
        <PlaceInput value={d.destination} onChange={(v) => d.set({ destination: v })} placeholder="Destination" icon="square" tint={colors.ink} />
        <DateTimeField value={d.departure} onChange={(v) => d.set({ departure: v })} />
        <FlexibilityPicker value={d.flexibleMinutes} onChange={(v) => d.set({ flexibleMinutes: v })} />
      </Card>
      <ErrorBanner error={explore.error ?? create.error ?? join.error} />
      <Section title={ready ? 'Matching rides' : 'Enter your trip above'}>
        {explore.isFetching && !explore.data ? <Loading /> : (
          <View style={{ gap: space.md }}>
            {explore.data?.map((g) => <GroupCard key={g.id} g={g} cta={{ label: 'Join this ride', loading: busy, onPress: () => joinGroup(g.id) }} />)}
            {ready && explore.data?.length === 0 && (
              <Empty icon="people-outline" title="No rides on your route yet" body="Post a request and we'll notify you the moment riders heading your way show up."
                action={<Button title="Post Ride Request" onPress={() => router.push('/request/new')} />} />
            )}
          </View>
        )}
      </Section>
    </Screen>
  );
}
