import { useLocalSearchParams, useRouter } from 'expo-router';

import { usePay, useRide } from '@/api/hooks';
import { Badge, Button, Card, ErrorBanner, Loading, Row, Screen, Spacer, Text } from '@/components/ui';
import { money2 } from '@/lib/format';
import { colors, space } from '@/theme';

/**
 * Payment authorisation. Funds are only *held* now and captured when the trip completes.
 * In production the Stripe SDK (PaymentSheet: cards, Apple Pay, Google Pay) confirms the PaymentIntent's
 * client_secret between create and confirm; card details never touch our servers.
 */
export default function Pay() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const rideId = Number(id);
  const router = useRouter();
  const ride = useRide(rideId);
  const pay = usePay();
  const fare = ride.data?.your_fare;
  if (!fare) return <Screen><Loading /></Screen>;
  return (
    <Screen footer={<Button title={`Authorise ${money2(fare.fare)}`} icon="lock-closed" loading={pay.isPending} onPress={() => pay.mutate(rideId, { onSuccess: () => router.back() })} />}>
      <Row style={{ justifyContent: 'space-between' }}><Text variant="title">Secure your seat</Text><Text variant="bodyBold" color={colors.brand} onPress={() => router.back()}>Close</Text></Row>
      <Spacer h={space.lg} />
      <ErrorBanner error={pay.error} />
      <Card>
        <Row style={{ justifyContent: 'space-between' }}><Text color={colors.inkSoft}>Your share</Text><Text>{money2(fare.fare - fare.platform_fee)}</Text></Row>
        <Row style={{ justifyContent: 'space-between' }}><Text color={colors.inkSoft}>Service fee</Text><Text>{money2(fare.platform_fee)}</Text></Row>
        <Spacer h={space.sm} />
        <Row style={{ justifyContent: 'space-between' }}><Text variant="h2">Total</Text><Text variant="h2">{money2(fare.fare)}</Text></Row>
      </Card>
      <Spacer />
      <Card tone="brand">
        <Text variant="bodyBold" color={colors.brandDark}>You're not charged yet</Text>
        <Text color={colors.inkSoft}>We place a hold now. The fare is captured when your trip is completed and the driver is paid.</Text>
      </Card>
      <Spacer />
      <Row gap={8}><Badge label="Card" icon="card" /><Badge label="Apple Pay — soon" /><Badge label="Google Pay — soon" /></Row>
      <Text variant="caption" color={colors.mute} style={{ marginTop: space.md }}>Test mode: the built-in fake gateway approves instantly. Set PAYMENT_PROVIDER=stripe to use Stripe.</Text>
    </Screen>
  );
}
