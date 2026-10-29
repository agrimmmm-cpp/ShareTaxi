import { useRouter } from 'expo-router';
import { useState } from 'react';

import { useAddContact, useContacts } from '@/api/hooks';
import { Button, Card, ErrorBanner, Field, Row, Screen, Section, Text } from '@/components/ui';
import { colors, space } from '@/theme';

export default function Contacts() {
  const router = useRouter();
  const q = useContacts();
  const add = useAddContact();
  const [name, setName] = useState('');
  const [phone, setPhone] = useState('');
  return (
    <Screen>
      <Row style={{ justifyContent: 'space-between' }}><Text variant="title">Emergency contacts</Text><Text variant="bodyBold" color={colors.brand} onPress={() => router.back()}>Back</Text></Row>
      <Text color={colors.mute} style={{ marginVertical: space.sm }}>They get your live trip link if you press SOS.</Text>
      {q.data?.map((c) => <Card key={c.id} style={{ marginBottom: space.sm }}><Text variant="bodyBold">{c.name}</Text><Text color={colors.mute}>{c.phone}</Text></Card>)}
      <Section title="Add a contact">
        <ErrorBanner error={add.error} />
        <Field placeholder="Name" value={name} onChangeText={setName} />
        <Field placeholder="Phone" value={phone} onChangeText={setPhone} keyboardType="phone-pad" />
        <Button title="Save contact" disabled={!name || !phone} loading={add.isPending} onPress={() => add.mutate({ name, phone }, { onSuccess: () => { setName(''); setPhone(''); } })} />
      </Section>
    </Screen>
  );
}
