import { Ionicons } from '@expo/vector-icons';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { useState } from 'react';
import { Pressable } from 'react-native';

import { useRate, useRide } from '@/api/hooks';
import { Button, Card, ErrorBanner, Field, Loading, Row, Screen, Section, Text } from '@/components/ui';
import { colors } from '@/theme';

function Stars({ value, onChange }: { value: number; onChange: (n: number) => void }) {
  return (
    <Row gap={6}>
      {[1, 2, 3, 4, 5].map((n) => (
        <Pressable key={n} onPress={() => onChange(n)} accessibilityLabel={`${n} stars`}>
          <Ionicons name={n <= value ? 'star' : 'star-outline'} size={32} color={n <= value ? '#F5B301' : colors.line} />
        </Pressable>
      ))}
    </Row>
  );
}

export default function Rate() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const rideId = Number(id);
  const router = useRouter();
  const ride = useRide(rideId);
  const rate = useRate();
  const [overall, setOverall] = useState(5);
  const [communication, setCommunication] = useState(5);
  const [punctuality, setPunctuality] = useState(5);
  const [safety, setSafety] = useState(5);
  const [comment, setComment] = useState('');
  const [queue, setQueue] = useState<number[]>([]);
  const r = ride.data;
  if (!r) return <Screen><Loading /></Screen>;
  // passengers rate the driver; the driver rates each passenger in turn
  const targets = r.is_driver ? r.passengers.map((p) => ({ id: p.user_id, name: p.first_name ?? p.label })) : [{ id: r.driver.user_id, name: r.driver.name }];
  const target = targets.find((t) => !queue.includes(t.id));
  const isDriverTarget = !r.is_driver;

  if (!target) return <Screen><Text variant="title">Thanks!</Text><Button title="Done" onPress={() => router.back()} style={{ marginTop: 16 }} /></Screen>;
  const submit = () =>
    rate.mutate(
      { ride_id: rideId, ratee_id: target.id, overall, communication, punctuality, safety: isDriverTarget ? safety : undefined, comment: comment || undefined },
      { onSuccess: () => { setQueue((q) => [...q, target.id]); setComment(''); } },
    );
  return (
    <Screen footer={<Button title="Submit rating" onPress={submit} loading={rate.isPending} />}>
      <Row style={{ justifyContent: 'space-between' }}><Text variant="title">Rate {target.name}</Text><Text variant="bodyBold" color={colors.brand} onPress={() => router.back()}>Later</Text></Row>
      <ErrorBanner error={rate.error} />
      <Section title="Overall"><Card><Stars value={overall} onChange={setOverall} /></Card></Section>
      <Section title="Communication"><Card><Stars value={communication} onChange={setCommunication} /></Card></Section>
      <Section title="Punctuality"><Card><Stars value={punctuality} onChange={setPunctuality} /></Card></Section>
      {isDriverTarget && <Section title="Safety & driving quality"><Card><Stars value={safety} onChange={setSafety} /></Card></Section>}
      <Section title="Review (optional)"><Field value={comment} onChangeText={setComment} placeholder="Share a few words" multiline /></Section>
    </Screen>
  );
}
