import { useRouter } from 'expo-router';

import { usePayments } from '@/api/hooks';
import { Badge, Card, Empty, Loading, Row, Screen, Text } from '@/components/ui';
import { dayLabel } from '@/lib/format';
import { colors, space } from '@/theme';

export default function Payments() {
  const router = useRouter();
  const q = usePayments();
  return (
    <Screen>
      <Row style={{ justifyContent: 'space-between', marginBottom: space.lg }}><Text variant="title">Payment history</Text><Text variant="bodyBold" color={colors.brand} onPress={() => router.back()}>Back</Text></Row>
      {q.isLoading ? <Loading /> : !q.data?.length ? <Empty icon="card-outline" title="No payments yet" /> : q.data.map((p) => (
        <Card key={p.id} onPress={() => router.push(`/ride/${p.ride_id}`)} style={{ marginBottom: space.sm }}>
          <Row style={{ justifyContent: 'space-between' }}>
            <View2 left={`Ride #${p.ride_id}`} sub={dayLabel(p.created_at)} />
            <Row gap={8}><Text variant="h2">${(p.amount_cents / 100).toFixed(2)}</Text><Badge label={p.status.replace('_', ' ')} tone={p.status === 'captured' ? 'savings' : p.status === 'refunded' ? 'info' : 'neutral'} /></Row>
          </Row>
          {p.cancellation_fee_cents > 0 && <Text variant="caption" color={colors.warn}>Includes cancellation fee</Text>}
        </Card>
      ))}
    </Screen>
  );
}

function View2({ left, sub }: { left: string; sub: string }) {
  return <Row gap={0} align="flex-start"><Text variant="bodyBold">{left}{'  '}</Text><Text color={colors.mute}>{sub}</Text></Row>;
}
