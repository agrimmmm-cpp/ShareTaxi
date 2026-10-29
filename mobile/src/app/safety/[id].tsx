import * as Linking from 'expo-linking';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { Alert, Share } from 'react-native';

import { API_URL, api } from '@/api/client';
import { useContacts, useRide } from '@/api/hooks';
import { Button, Card, Row, Screen, Section, Text } from '@/components/ui';
import { colors, space } from '@/theme';

export default function Safety() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const rideId = Number(id);
  const router = useRouter();
  const ride = useRide(rideId).data;
  const contacts = useContacts();

  const shareTrip = () => ride?.share_token && Share.share({ message: `Follow my ShareTaxi trip live: ${API_URL}/share/${ride.share_token}` });
  const sos = async () => {
    try {
      const res = await api<{ notified_contacts: string[]; share_token: string | null }>('/safety/sos', { method: 'POST', body: { ride_id: rideId } });
      Alert.alert('SOS sent', res.notified_contacts.length ? `Safety team alerted. ${res.notified_contacts.join(', ')} can follow your trip.` : 'Safety team alerted. Add emergency contacts in Profile.');
    } catch (e) { Alert.alert('Could not send SOS', e instanceof Error ? e.message : ''); }
  };
  const report = () =>
    Alert.alert('Report an issue', 'What happened?', ['safety', 'conduct', 'payment', 'other'].map((category) => ({
      text: category[0].toUpperCase() + category.slice(1),
      onPress: () => void api('/safety/report', { method: 'POST', body: { category, ride_id: rideId } }).then(() => Alert.alert('Thanks', 'Our team will review this.')),
    })));

  return (
    <Screen>
      <Row style={{ justifyContent: 'space-between' }}><Text variant="title">Safety</Text><Text variant="bodyBold" color={colors.brand} onPress={() => router.back()}>Close</Text></Row>
      <Section title="Emergency">
        <Button title="Call emergency services" variant="danger" icon="call" onPress={() => void Linking.openURL('tel:911')} />
        <Button title="Send SOS to ShareTaxi" variant="danger" icon="warning" onPress={sos} style={{ marginTop: space.md }} />
      </Section>
      <Section title="Share your trip">
        <Card><Text color={colors.inkSoft}>Friends and family get a live link with your driver, vehicle and next stop. No account needed.</Text>
          <Button title="Share live trip" icon="share-outline" variant="secondary" onPress={shareTrip} style={{ marginTop: space.md }} /></Card>
      </Section>
      <Section title="Emergency contacts" action={{ label: 'Manage', onPress: () => router.push('/contacts') }}>
        <Card>{contacts.data?.length ? contacts.data.map((c) => <Text key={c.id} variant="bodyBold">{c.name} <Text color={colors.mute}>{c.phone}</Text></Text>) : <Text color={colors.mute}>None yet. Add someone we should alert.</Text>}</Card>
      </Section>
      <Section title="Something wrong?"><Button title="Report a problem" variant="secondary" icon="flag-outline" onPress={report} /></Section>
    </Screen>
  );
}
