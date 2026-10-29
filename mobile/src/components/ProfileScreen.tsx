import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { Pressable, View } from 'react-native';

import { useDriverMe } from '@/api/hooks';
import { useAuth } from '@/store/auth';
import { colors, space } from '@/theme';

import { ModeToggle } from './ModeToggle';
import { Badge, Button, Card, Divider, Row, Screen, Spacer, Text } from './ui';

function Item({ icon, label, hint, onPress }: { icon: keyof typeof Ionicons.glyphMap; label: string; hint?: string; onPress: () => void }) {
  return (
    <Pressable onPress={onPress} style={{ flexDirection: 'row', alignItems: 'center', paddingVertical: 14, gap: 14 }}>
      <Ionicons name={icon} size={22} color={colors.inkSoft} />
      <View style={{ flex: 1 }}><Text variant="bodyBold">{label}</Text>{hint && <Text variant="caption" color={colors.mute}>{hint}</Text>}</View>
      <Ionicons name="chevron-forward" size={18} color={colors.mute} />
    </Pressable>
  );
}

export function ProfileScreen() {
  const { me, signOut } = useAuth();
  const router = useRouter();
  const driver = useDriverMe();
  if (!me) return null;
  const isDriver = me.roles.includes('driver');
  const status = driver.data?.status;
  return (
    <Screen>
      <Row gap={14}>
        <View style={{ width: 64, height: 64, borderRadius: 32, backgroundColor: colors.brandSoft, alignItems: 'center', justifyContent: 'center' }}>
          <Text variant="title" color={colors.brand}>{me.full_name.slice(0, 1)}</Text>
        </View>
        <View style={{ flex: 1 }}>
          <Text variant="title">{me.full_name}</Text>
          <Text color={colors.mute}>{me.email}</Text>
          <Row gap={6} style={{ marginTop: 4 }}>
            <Badge label={me.rating_count ? `★ ${me.rating_avg.toFixed(1)} (${me.rating_count})` : 'New'} tone="warn" />
            {me.email_verified && <Badge label="Email" tone="savings" icon="checkmark" />}
            {me.phone_verified && <Badge label="Phone" tone="savings" icon="checkmark" />}
          </Row>
        </View>
      </Row>
      <Spacer />
      <ModeToggle />
      {!isDriver && (
        <Card tone="driver" style={{ marginTop: space.lg }}>
          <Text variant="h2" color={colors.driver}>Drive & Earn</Text>
          <Text color={colors.inkSoft} style={{ marginVertical: 6 }}>
            {status === 'pending' ? "Your documents are under review. We'll notify you when you're approved." : 'Heading somewhere anyway? Post your trip and let ShareTaxi fill your seats.'}
          </Text>
          <Button title={status ? 'Continue verification' : 'Become a driver'} variant="driver" small onPress={() => router.push('/driver/apply')} />
        </Card>
      )}
      <Card style={{ marginTop: space.lg, paddingVertical: space.sm }}>
        <Item icon="notifications-outline" label="Notifications" onPress={() => router.push('/notifications')} />
        <Divider />
        <Item icon="card-outline" label="Payment history" hint="Apple Pay & Google Pay coming soon" onPress={() => router.push('/payments')} />
        <Divider />
        <Item icon="shield-checkmark-outline" label="Emergency contacts" hint="Notified if you press SOS" onPress={() => router.push('/contacts')} />
        <Divider />
        <Item icon="repeat-outline" label="Recurring commutes" onPress={() => router.push('/recurring')} />
      </Card>
      <Spacer />
      <Button title="Sign out" variant="secondary" icon="log-out-outline" onPress={() => void signOut()} />
    </Screen>
  );
}
