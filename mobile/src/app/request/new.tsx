import { useRouter } from 'expo-router';
import { useState } from 'react';
import { Switch, View } from 'react-native';

import { useCreateRequest } from '@/api/hooks';
import { DateTimeField, FlexibilityPicker, PlaceInput } from '@/components/inputs';
import { Button, Card, Chip, ErrorBanner, Field, Row, Screen, Section, Stepper, Text } from '@/components/ui';
import { useDraft } from '@/store/draft';
import { colors, space } from '@/theme';

export default function NewRequest() {
  const router = useRouter();
  const d = useDraft();
  const create = useCreateRequest();
  const [luggage, setLuggage] = useState(0);
  const [accessible, setAccessible] = useState(false);
  const [accessNote, setAccessNote] = useState('');
  const [pickupDev, setPickupDev] = useState(10);
  const [detour, setDetour] = useState(25);
  const [type, setType] = useState<'shared' | 'request'>('shared');
  const [notes, setNotes] = useState('');
  const valid = d.origin.trim().length > 1 && d.destination.trim().length > 1;

  const submit = () =>
    create.mutate(
      {
        origin_address: d.origin.trim(), destination_address: d.destination.trim(), preferred_departure: d.departure.toISOString(),
        flexible_minutes: d.flexibleMinutes, passenger_count: d.passengers, luggage_count: luggage,
        accessibility_needs: accessible ? accessNote || 'Accessibility support needed' : null,
        max_pickup_deviation_min: pickupDev, maximum_detour_minutes: detour, ride_type: type, notes: notes || null,
      },
      { onSuccess: (r) => { d.reset(); router.replace(`/request/${r.id}`); } },
    );

  return (
    <Screen footer={<Button title="Post & find riders" icon="search" onPress={submit} loading={create.isPending} disabled={!valid} />}>
      <Row style={{ justifyContent: 'space-between' }}>
        <Text variant="title">Post a ride request</Text>
        <Text variant="bodyBold" color={colors.brand} onPress={() => router.back()}>Close</Text>
      </Row>
      <Text color={colors.mute} style={{ marginBottom: space.lg }}>We'll search for riders heading your way right away.</Text>
      <ErrorBanner error={create.error} />
      <Card style={{ gap: space.md }}>
        <PlaceInput value={d.origin} onChange={(v) => d.set({ origin: v })} placeholder="Pickup" icon="radio-button-on" />
        <PlaceInput value={d.destination} onChange={(v) => d.set({ destination: v })} placeholder="Destination" icon="square" tint={colors.ink} />
      </Card>
      <Section title="When">
        <Card style={{ gap: space.md }}>
          <DateTimeField value={d.departure} onChange={(v) => d.set({ departure: v })} />
          <Text variant="label" color={colors.mute}>Flexible time</Text>
          <FlexibilityPicker value={d.flexibleMinutes} onChange={(v) => d.set({ flexibleMinutes: v })} />
        </Card>
      </Section>
      <Section title="Who & what">
        <Card style={{ gap: space.lg }}>
          <Row style={{ justifyContent: 'space-between' }}><Text variant="bodyBold">Passengers</Text><Stepper value={d.passengers} min={1} max={4} onChange={(v) => d.set({ passengers: v })} /></Row>
          <Row style={{ justifyContent: 'space-between' }}><Text variant="bodyBold">Luggage</Text><Stepper value={luggage} min={0} max={6} onChange={setLuggage} /></Row>
          <Row style={{ justifyContent: 'space-between' }}><Text variant="bodyBold">Accessibility needs</Text><Switch value={accessible} onValueChange={setAccessible} trackColor={{ true: colors.brand }} /></Row>
          {accessible && <Field placeholder="e.g. wheelchair folding, guide dog" value={accessNote} onChangeText={setAccessNote} />}
        </Card>
      </Section>
      <Section title="Your limits">
        <Card style={{ gap: space.lg }}>
          <View><Row style={{ justifyContent: 'space-between' }}><Text variant="bodyBold">Max pickup deviation</Text><Stepper value={pickupDev} min={0} max={30} step={5} format={(v) => `${v} min`} onChange={setPickupDev} /></Row></View>
          <View><Row style={{ justifyContent: 'space-between' }}><Text variant="bodyBold">Max travel-time detour</Text><Stepper value={detour} min={5} max={60} step={5} format={(v) => `${v} min`} onChange={setDetour} /></Row>
            <Text variant="caption" color={colors.mute} style={{ marginTop: 6 }}>Longer detours mean more riders can join, which lowers everyone's fare.</Text></View>
        </Card>
      </Section>
      <Section title="Ride type">
        <Row><Chip label="Shared ride" icon="people" selected={type === 'shared'} onPress={() => setType('shared')} /><Chip label="Request & wait" icon="hourglass-outline" selected={type === 'request'} onPress={() => setType('request')} /></Row>
        <Text variant="caption" color={colors.mute} style={{ marginTop: 8 }}>{type === 'shared' ? 'Join riders already forming on your route.' : 'Post your trip and wait for others to join you.'}</Text>
      </Section>
      <Section title="Notes for your driver"><Field placeholder="Optional" value={notes} onChangeText={setNotes} multiline /></Section>
    </Screen>
  );
}
