import { View } from 'react-native';

import { colors, radius } from '@/theme';

import type { MapLine, MapMarker } from './MapRoute';
import { Text } from './ui';

export type { MapLine, MapMarker };

/** react-native-maps has no web build; show a placeholder so the web target still bundles. */
export function MapRoute({ height = 280, markers = [] }: { lines?: MapLine[]; markers?: MapMarker[]; height?: number; rounded?: boolean }) {
  return (
    <View style={{ height, borderRadius: radius.lg, backgroundColor: colors.brandSoft, alignItems: 'center', justifyContent: 'center', padding: 16 }}>
      <Text variant="bodyBold" color={colors.brandDark}>Map preview (native only)</Text>
      <Text variant="caption" color={colors.inkSoft}>{markers.map((m) => m.label).filter(Boolean).join(' → ')}</Text>
    </View>
  );
}
