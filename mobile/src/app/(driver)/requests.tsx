import { useRouter } from 'expo-router';
import { useState } from 'react';
import { View } from 'react-native';

import { useDemand } from '@/api/hooks';
import { MapRoute } from '@/components/MapRoute';
import { Badge, Button, Card, Empty, Loading, Row, Screen, Text } from '@/components/ui';
import { windowLabel } from '@/lib/format';
import { useDraft } from '@/store/draft';
import { colors, space } from '@/theme';

/** Reverse marketplace: tap a demand cluster to offer a ride for exactly that route. */
export default function Requests() {
  const router = useRouter();
  const demand = useDemand();
  const draft = useDraft();
  const [sel, setSel] = useState<number | null>(null);
  const clusters = demand.data ?? [];
  const chosen = sel != null ? clusters[sel] : null;
  const color = (l: string) => (l === 'high' ? colors.danger : l === 'medium' ? colors.warn : colors.mute);
  return (
    <Screen bg="#F4F3FC">
      <Text variant="title">Ride requests</Text>
      <Text color={colors.mute} style={{ marginBottom: space.lg }}>Where riders are waiting right now</Text>
      <MapRoute height={230} markers={clusters.map((c, i) => ({ id: String(i), lat: c.origin_lat, lng: c.origin_lng, label: String(c.passengers), kind: 'demand', color: color(c.level) }))}
        lines={chosen ? [{ id: 'sel', coords: [{ latitude: chosen.origin_lat, longitude: chosen.origin_lng }, { latitude: chosen.destination_lat, longitude: chosen.destination_lng }], color: colors.driver, dashed: true }] : []} />
      <View style={{ gap: space.md, marginTop: space.lg }}>
        {demand.isLoading && <Loading />}
        {!demand.isLoading && !clusters.length && <Empty icon="people-outline" title="No open requests right now" body="Check back soon, or post your trip and riders will find you." />}
        {clusters.map((c, i) => (
          <Card key={i} onPress={() => setSel(i)} style={sel === i ? { borderWidth: 2, borderColor: colors.driver } : undefined}>
            <Row style={{ justifyContent: 'space-between' }}>
              <View style={{ flex: 1 }}><Text variant="h2">{c.origin_area} → {c.destination_area}</Text><Text color={colors.mute}>{windowLabel(c.window_start, c.window_end)}</Text></View>
              <Badge label={`${c.passengers} looking`} icon="people" tone={c.level === 'high' ? 'danger' : c.level === 'medium' ? 'warn' : 'neutral'} />
            </Row>
            {sel === i && <Button title="Offer a ride on this route" variant="driver" small style={{ marginTop: space.md }}
              onPress={() => { draft.set({ origin: c.origin_area, destination: c.destination_area, departure: new Date(new Date(c.window_start.endsWith('Z') ? c.window_start : c.window_start + 'Z').getTime() + 30 * 60_000) }); router.push('/driver/new-trip'); }} />}
          </Card>
        ))}
      </View>
    </Screen>
  );
}
