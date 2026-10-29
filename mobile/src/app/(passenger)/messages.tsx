import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { Pressable, View } from 'react-native';

import { useRides } from '@/api/hooks';
import { Empty, Loading, Row, Screen, Text } from '@/components/ui';
import { dayLabel, timeLabel } from '@/lib/format';
import { colors, space } from '@/theme';

export function RideChats({ role }: { role: 'passenger' | 'driver' }) {
  const router = useRouter();
  const rides = useRides(role);
  if (rides.isLoading) return <Screen><Loading /></Screen>;
  const chats = (rides.data ?? []).filter((r) => r.status !== 'cancelled');
  return (
    <Screen>
      <Text variant="title" style={{ marginBottom: space.lg }}>Messages</Text>
      {chats.length === 0 ? <Empty icon="chatbubbles-outline" title="No conversations yet" body="Group chat opens as soon as your ride is confirmed." /> : chats.map((r) => (
        <Pressable key={r.id} onPress={() => router.push(`/chat/${r.id}`)} style={{ paddingVertical: space.md }}>
          <Row gap={14}>
            <View style={{ width: 48, height: 48, borderRadius: 24, backgroundColor: colors.brandSoft, alignItems: 'center', justifyContent: 'center' }}><Ionicons name="people" size={22} color={colors.brand} /></View>
            <View style={{ flex: 1 }}><Text variant="bodyBold" numberOfLines={1}>{r.headline}</Text><Text variant="caption" color={colors.mute}>{dayLabel(r.scheduled_departure)} {timeLabel(r.scheduled_departure)} · {r.passenger_count} riders + driver</Text></View>
            <Ionicons name="chevron-forward" size={18} color={colors.mute} />
          </Row>
        </Pressable>
      ))}
    </Screen>
  );
}

export default function Messages() {
  return <RideChats role="passenger" />;
}
