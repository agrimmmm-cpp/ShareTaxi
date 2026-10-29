import { useRouter } from 'expo-router';
import { useState } from 'react';
import { Switch } from 'react-native';

import { useCreateTrip, useDriverMe } from '@/api/hooks';
import { DateTimeField, PlaceInput } from '@/components/inputs';
import { Button, Card, ErrorBanner, Row, Screen, Section, Stepper, Text } from '@/components/ui';
import { useDraft } from '@/store/draft';
import { colors, space } from '@/theme';

export default function NewTrip() {
  const router = useRouter();
  const draft = useDraft();
  const me = useDriverMe();
  const create = useCreateTrip();
  const [seats, setSeats] = useState(3);
  const [detour, setDetour] = useState(30);
  const [minEarn, setMinEarn] = useState(55);
  const [auto, setAuto] = useState(true);
  const vehicle = me.data?.vehicles?.[0];
  const valid = draft.origin.trim().length > 1 && draft.destination.trim().length > 1 && !!vehicle;
  return (
    <Screen bg="#F4F3FC" footer={<Button variant="driver" title="Post trip & find passengers" icon="people" disabled={!valid} loading={create.isPending}
      onPress={() => create.mutate({ vehicle_id: vehicle!.id, origin_address: draft.origin.trim(), destination_address: draft.destination.trim(), departure_time: draft.departure.toISOString(),
        available_seats: seats, maximum_detour_minutes: detour, minimum_earnings: minEarn, auto_match: auto },
        { onSuccess: (t) => { draft.reset(); router.replace(`/driver/trip/${t.id}`); } })} />}>
      <Row style={{ justifyContent: 'space-between' }}><Text variant="title">Post a trip</Text><Text variant="bodyBold" color={colors.driver} onPress={() => router.back()}>Close</Text></Row>
      <Text color={colors.mute} style={{ marginBottom: space.lg }}>We compare your route against waiting riders and recommend the best groups.</Text>
      <ErrorBanner error={create.error} />
      <Card style={{ gap: space.md }}>
        <PlaceInput value={draft.origin} onChange={(v) => draft.set({ origin: v })} placeholder="Starting point" icon="radio-button-on" tint={colors.driver} />
        <PlaceInput value={draft.destination} onChange={(v) => draft.set({ destination: v })} placeholder="Destination" icon="square" tint={colors.ink} />
      </Card>
      <Section title="Departure"><Card><DateTimeField value={draft.departure} onChange={(v) => draft.set({ departure: v })} /></Card></Section>
      <Section title="Seats & route">
        <Card style={{ gap: space.lg }}>
          <Row style={{ justifyContent: 'space-between' }}><Text variant="bodyBold">Available seats</Text><Stepper value={seats} min={1} max={vehicle?.seats ?? 4} onChange={setSeats} /></Row>
          <Row style={{ justifyContent: 'space-between' }}><Text variant="bodyBold">Max detour</Text><Stepper value={detour} min={5} max={60} step={5} format={(v) => `${v} min`} onChange={setDetour} /></Row>
          <Row style={{ justifyContent: 'space-between' }}><Text variant="bodyBold">Minimum earnings</Text><Stepper value={minEarn} min={0} max={500} step={5} format={(v) => `$${v}`} onChange={setMinEarn} /></Row>
          <Text variant="caption" color={colors.mute}>We never propose a group that leaves you below this (after the platform fee and fuel/wear costs).</Text>
          <Row style={{ justifyContent: 'space-between' }}><Text variant="bodyBold">Automatic passenger matching</Text><Switch value={auto} onValueChange={setAuto} trackColor={{ true: colors.driver }} /></Row>
        </Card>
      </Section>
      {!vehicle && <Text color={colors.danger}>Add a vehicle first (Profile → Drive & Earn).</Text>}
    </Screen>
  );
}
