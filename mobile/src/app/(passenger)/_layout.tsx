import { Tabs } from 'expo-router';

import { tab } from '@/components/tabIcon';
import { colors } from '@/theme';

export default function PassengerTabs() {
  return (
    <Tabs screenOptions={{ headerShown: false, tabBarActiveTintColor: colors.brand, tabBarInactiveTintColor: colors.mute, tabBarStyle: { borderTopColor: colors.line, height: 62, paddingTop: 6 }, tabBarLabelStyle: { fontWeight: '600' } }}>
      <Tabs.Screen name="index" options={tab('Home', 'home-outline', 'home')} />
      <Tabs.Screen name="rides" options={tab('My Rides', 'car-outline', 'car')} />
      <Tabs.Screen name="explore" options={tab('Explore', 'compass-outline', 'compass')} />
      <Tabs.Screen name="messages" options={tab('Messages', 'chatbubbles-outline', 'chatbubbles')} />
      <Tabs.Screen name="profile" options={tab('Profile', 'person-outline', 'person')} />
    </Tabs>
  );
}
