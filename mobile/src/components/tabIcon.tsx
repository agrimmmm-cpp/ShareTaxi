import { Ionicons } from '@expo/vector-icons';
import type { ColorValue } from 'react-native';

type IconName = keyof typeof Ionicons.glyphMap;

/** Screen options for a tab: title + outline/filled icon pair. */
export const tab = (title: string, icon: IconName, active: IconName) => ({
  title,
  tabBarIcon: ({ color, focused, size }: { color: ColorValue; focused: boolean; size: number }) => (
    <Ionicons name={focused ? active : icon} size={size} color={color as string} />
  ),
});
