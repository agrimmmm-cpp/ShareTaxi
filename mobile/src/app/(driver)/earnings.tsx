import { useEarnings } from '@/api/hooks';
import { Badge, Card, Empty, Loading, Row, Screen, Section, Text } from '@/components/ui';
import { dayLabel } from '@/lib/format';
import { colors, space } from '@/theme';

export default function Earnings() {
  const q = useEarnings();
  return (
    <Screen bg="#F4F3FC">
      <Text variant="title" style={{ marginBottom: space.lg }}>Earnings</Text>
      {!q.data ? <Loading /> : (
        <>
          <Card tone="driver"><Text variant="label" color={colors.driver}>Total paid out</Text><Text variant="display" color={colors.driver}>${q.data.total.toFixed(2)}</Text>
            {q.data.pending > 0 && <Text color={colors.inkSoft}>${q.data.pending.toFixed(2)} pending</Text>}</Card>
          <Section title="Payouts">
            {q.data.payouts.length ? q.data.payouts.map((p) => (
              <Card key={p.id} style={{ marginBottom: space.sm, paddingVertical: space.md }}>
                <Row style={{ justifyContent: 'space-between' }}><Text variant="bodyBold">Ride #{p.ride_id} · {dayLabel(p.created_at)}</Text><Row gap={8}><Text variant="h2">${(p.amount_cents / 100).toFixed(2)}</Text><Badge label={p.status} tone={p.status === 'paid' ? 'savings' : 'warn'} /></Row></Row>
              </Card>
            )) : <Empty icon="wallet-outline" title="No payouts yet" body="You're paid automatically after each completed trip." />}
          </Section>
          <Text variant="caption" color={colors.mute}>Payouts are sent after the trip completes and payments are captured, minus the platform fee.</Text>
        </>
      )}
    </Screen>
  );
}
