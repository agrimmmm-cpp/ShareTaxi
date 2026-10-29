import { useRouter } from 'expo-router';
import { ReactNode, useState } from 'react';
import { View } from 'react-native';

import { useDriverApply, useDriverMe, useSubmitDocument } from '@/api/hooks';
import { useAuth } from '@/store/auth';
import { Badge, Button, Card, ErrorBanner, Field, Loading, Row, Screen, Section, Text } from '@/components/ui';
import { colors, space } from '@/theme';

const DOC_LABEL: Record<string, string> = { drivers_licence: "Driver's licence", vehicle_registration: 'Vehicle registration', insurance: 'Insurance', identity: 'Identity verification' };

export default function Apply() {
  const router = useRouter();
  const me = useDriverMe();
  const apply = useDriverApply();
  const submit = useSubmitDocument();
  const refreshMe = useAuth((s) => s.refreshMe);
  const [v, setV] = useState({ make: '', model: '', year: '2021', color: '', license_plate: '', seats: '4' });
  const set = (k: keyof typeof v) => (t: string) => setV((p) => ({ ...p, [k]: t }));
  const d = me.data;
  if (me.isLoading) return <Screen><Loading /></Screen>;

  return (
    <Screen>
      <Row style={{ justifyContent: 'space-between' }}><Text variant="title">Drive & Earn</Text><Text variant="bodyBold" color={colors.brand} onPress={() => router.back()}>Close</Text></Row>
      {!d?.is_driver ? (
        <>
          <Text color={colors.inkSoft} style={{ marginVertical: space.md }}>Tell us about your vehicle. Next you'll upload your documents for verification.</Text>
          <ErrorBanner error={apply.error} />
          <Field label="Make" value={v.make} onChangeText={set('make')} placeholder="Toyota" />
          <Field label="Model" value={v.model} onChangeText={set('model')} placeholder="Prius" />
          <Row><View2><Field label="Year" value={v.year} onChangeText={set('year')} keyboardType="number-pad" /></View2><View2><Field label="Seats for riders" value={v.seats} onChangeText={set('seats')} keyboardType="number-pad" /></View2></Row>
          <Field label="Colour" value={v.color} onChangeText={set('color')} />
          <Field label="Licence plate" value={v.license_plate} onChangeText={set('license_plate')} autoCapitalize="characters" />
          <Button title="Continue" variant="driver" loading={apply.isPending} disabled={!v.make || !v.model || !v.color || !v.license_plate}
            onPress={() => apply.mutate({ ...v, year: Number(v.year), seats: Number(v.seats) })} />
        </>
      ) : (
        <>
          <Row gap={8} style={{ marginVertical: space.md }}><Text>Status</Text><Badge label={d.status ?? ''} tone={d.status === 'approved' ? 'savings' : d.status === 'rejected' ? 'danger' : 'warn'} /></Row>
          <ErrorBanner error={submit.error} />
          {d.status === 'approved' ? <Button title="You're verified — go to driver mode" variant="driver" onPress={async () => { await refreshMe(); useAuth.getState().setMode('driver'); router.replace('/(driver)/dashboard'); }} /> : (
            <Section title="Verification documents">
              {(d.required_documents ?? []).map((t) => {
                const doc = d.documents?.filter((x) => x.doc_type === t).at(-1);
                return (
                  <Card key={t} style={{ marginBottom: space.sm }}>
                    <Row style={{ justifyContent: 'space-between' }}>
                      <Text variant="bodyBold">{DOC_LABEL[t] ?? t}</Text>
                      {doc ? <Badge label={doc.status} tone={doc.status === 'approved' ? 'savings' : doc.status === 'rejected' ? 'danger' : 'warn'} /> :
                        <Button title="Upload" small variant="secondary" loading={submit.isPending} onPress={() => submit.mutate({ doc_type: t, file_url: `local://${t}.jpg` })} />}
                    </Row>
                    {doc?.review_notes && <Text variant="caption" color={colors.danger}>{doc.review_notes}</Text>}
                  </Card>
                );
              })}
              <Text variant="caption" color={colors.mute}>Dev build uploads a placeholder file; production wires this to your document store and a provider such as Persona or Stripe Identity (see verification_service.py).</Text>
            </Section>
          )}
        </>
      )}
    </Screen>
  );
}

const View2 = ({ children }: { children: ReactNode }) => <View style={{ flex: 1 }}>{children}</View>;
