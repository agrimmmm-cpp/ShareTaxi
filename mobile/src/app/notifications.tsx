import { useRouter } from 'expo-router';
import { View } from 'react-native';

import { api } from '@/api/client';
import { useNotifications } from '@/api/hooks';
import { Card, Empty, Loading, Row, Screen, Text } from '@/components/ui';
import { dayLabel, timeLabel } from '@/lib/format';
import { colors, space } from '@/theme';
import { useQueryClient } from '@tanstack/react-query';
import { useEffect } from 'react';

export default function Notifications() {
  const router = useRouter();
  const qc = useQueryClient();
  const q = useNotifications();
  useEffect(() => { void api('/notifications/read-all', { method: 'POST' }).then(() => qc.invalidateQueries({ queryKey: ['notifications'] })); }, [qc]);
  return (
    <Screen>
      <Row style={{ justifyContent: 'space-between', marginBottom: space.lg }}><Text variant="title">Notifications</Text><Text variant="bodyBold" color={colors.brand} onPress={() => router.back()}>Back</Text></Row>
      {q.isLoading ? <Loading /> : !q.data?.length ? <Empty icon="notifications-outline" title="All caught up" body="Match updates, driver news and receipts show up here." /> : (
        <View style={{ gap: space.sm }}>
          {q.data.map((n) => (
            <Card key={n.id} style={{ paddingVertical: space.md }} onPress={() => {
              const d = n.data as { ride_id?: number; group_id?: number; trip_id?: number } | null;
              if (d?.ride_id) router.push(`/ride/${d.ride_id}`); else if (d?.trip_id) router.push(`/driver/trip/${d.trip_id}`);
            }}>
              <Row style={{ justifyContent: 'space-between' }}><Text variant="bodyBold" style={{ flex: 1 }}>{n.title}</Text>{!n.read_at && <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: colors.brand }} />}</Row>
              <Text color={colors.inkSoft}>{n.body}</Text>
              <Text variant="caption" color={colors.mute}>{dayLabel(n.created_at)} {timeLabel(n.created_at)}</Text>
            </Card>
          ))}
        </View>
      )}
    </Screen>
  );
}
