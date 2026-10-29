import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useRouter } from 'expo-router';
import { useState } from 'react';

import { api } from '@/api/client';
import { PlaceInput } from '@/components/inputs';
import { Button, Card, Chip, ErrorBanner, Row, Screen, Section, Text } from '@/components/ui';
import { colors, space } from '@/theme';

interface Recurring { id: number; kind: string; days_of_week: string; time_of_day: string; active: boolean; template: { origin_address: string; destination_address: string } }
const DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];

export default function RecurringScreen() {
  const router = useRouter();
  const qc = useQueryClient();
  const list = useQuery({ queryKey: ['recurring'], queryFn: () => api<Recurring[]>('/recurring') });
  const [origin, setOrigin] = useState('');
  const [dest, setDest] = useState('');
  const [days, setDays] = useState<number[]>([0, 2, 4]);
  const [time, setTime] = useState('08:00');
  const [err, setErr] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  const create = async () => {
    setBusy(true); setErr(null);
    try {
      await api('/recurring', { method: 'POST', body: { kind: 'passenger', days_of_week: days, time_of_day: time, template: { origin_address: origin, destination_address: dest, maximum_detour_minutes: 25, flexible_minutes: 30 } } });
      setOrigin(''); setDest('');
      await qc.invalidateQueries({ queryKey: ['recurring'] });
      await qc.invalidateQueries({ queryKey: ['requests'] });
    } catch (e) { setErr(e); } finally { setBusy(false); }
  };
  const stop = async (id: number) => { await api(`/recurring/${id}`, { method: 'DELETE' }); void qc.invalidateQueries({ queryKey: ['recurring'] }); };

  return (
    <Screen>
      <Row style={{ justifyContent: 'space-between' }}><Text variant="title">Recurring commutes</Text><Text variant="bodyBold" color={colors.brand} onPress={() => router.back()}>Back</Text></Row>
      <Text color={colors.mute} style={{ marginVertical: space.sm }}>We post next week's rides for you and group you with the same riders when we can.</Text>
      {list.data?.filter((r) => r.active).map((r) => (
        <Card key={r.id} style={{ marginBottom: space.sm }}>
          <Text variant="bodyBold">{r.template.origin_address} → {r.template.destination_address}</Text>
          <Text color={colors.mute}>{r.days_of_week.split(',').map((d) => DAYS[Number(d)]).join(', ')} · {r.time_of_day}</Text>
          <Text variant="bodyBold" color={colors.danger} onPress={() => void stop(r.id)} style={{ marginTop: 6 }}>Stop repeating</Text>
        </Card>
      ))}
      <Section title="New commute">
        <ErrorBanner error={err} />
        <Card style={{ gap: space.md }}>
          <PlaceInput value={origin} onChange={setOrigin} placeholder="From" icon="radio-button-on" />
          <PlaceInput value={dest} onChange={setDest} placeholder="To" icon="square" tint={colors.ink} />
          <Row gap={6} style={{ flexWrap: 'wrap' }}>{DAYS.map((d, i) => <Chip key={d} label={d} selected={days.includes(i)} onPress={() => setDays((p) => (p.includes(i) ? p.filter((x) => x !== i) : [...p, i]))} />)}</Row>
          <Row gap={6} style={{ flexWrap: 'wrap' }}>{['07:00', '08:00', '09:00', '17:00', '18:00'].map((t) => <Chip key={t} label={t} selected={time === t} onPress={() => setTime(t)} />)}</Row>
          <Button title="Repeat weekly" disabled={!origin || !dest || !days.length} loading={busy} onPress={() => void create()} />
        </Card>
      </Section>
    </Screen>
  );
}
