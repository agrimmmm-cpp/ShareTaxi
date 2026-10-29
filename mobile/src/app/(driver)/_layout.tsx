import { Tabs } from 'expo-router';

import { tab } from '@/components/tabIcon';
import { colors } from '@/theme';

export default function DriverTabs() {
  return (
    <Tabs screenOptions={{ headerShown: false, tabBarActiveTintColor: colors.driver, tabBarInactiveTintColor: colors.mute, tabBarStyle: { borderTopColor: colors.line, height: 62, paddingTop: 6 }, tabBarLabelStyle: { fontWeight: '600' } }}>
      <Tabs.Screen name="dashboard" options={tab('Dashboard', 'speedometer-outline', 'speedometer')} />
      <Tabs.Screen name="requests" options={tab('Requests', 'people-outline', 'people')} />
      <Tabs.Screen name="trips" options={tab('My Trips', 'map-outline', 'map')} />
      <Tabs.Screen name="earnings" options={tab('Earnings', 'wallet-outline', 'wallet')} />
      <Tabs.Screen name="profile" options={tab('Profile', 'person-outline', 'person')} />
    </Tabs>
  );
}
