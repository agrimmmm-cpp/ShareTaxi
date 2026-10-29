import { Ionicons } from '@expo/vector-icons';
import { useRef, useState } from 'react';
import { FlatList, View, useWindowDimensions } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { Button, Row, Text } from '@/components/ui';
import { useAuth } from '@/store/auth';
import { colors, radius, space } from '@/theme';

const SLIDES = [
  { icon: 'people', title: 'Share the ride.\nShare the cost.', body: 'Heading somewhere planned? Go with people already going your way.' },
  { icon: 'navigate', title: "Tell us where\nyou're going.", body: 'Post your trip once: pickup, destination and when. Flexible timing means better matches.' },
  { icon: 'git-merge', title: "We'll find people\nheading your way.", body: 'We compare routes, not just addresses, and group riders with minimal detours.' },
  { icon: 'wallet', title: 'Split the trip\nand save.', body: 'Pay for the distance you ride. Drivers still earn what makes the trip worthwhile.' },
] as const;

export default function Onboarding() {
  const { width } = useWindowDimensions();
  const [i, setI] = useState(0);
  const ref = useRef<FlatList>(null);
  const finish = useAuth((s) => s.finishOnboarding);
  const last = i === SLIDES.length - 1;
  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: colors.white }}>
      <FlatList
        ref={ref} data={SLIDES} horizontal pagingEnabled showsHorizontalScrollIndicator={false} keyExtractor={(s) => s.title}
        onMomentumScrollEnd={(e) => setI(Math.round(e.nativeEvent.contentOffset.x / width))}
        renderItem={({ item }) => (
          <View style={{ width, padding: space.xl, justifyContent: 'center', gap: space.xl }}>
            <View style={{ width: 112, height: 112, borderRadius: radius.xl, backgroundColor: colors.brandSoft, alignItems: 'center', justifyContent: 'center' }}>
              <Ionicons name={item.icon} size={52} color={colors.brand} />
            </View>
            <Text variant="display">{item.title}</Text>
            <Text color={colors.inkSoft} style={{ fontSize: 17, lineHeight: 25 }}>{item.body}</Text>
          </View>
        )}
      />
      <View style={{ padding: space.xl, gap: space.lg }}>
        <Row style={{ justifyContent: 'center' }} gap={8}>
          {SLIDES.map((_, k) => <View key={k} style={{ width: k === i ? 24 : 8, height: 8, borderRadius: 4, backgroundColor: k === i ? colors.brand : colors.line }} />)}
        </Row>
        <Button title={last ? 'Get Started' : 'Next'} onPress={() => (last ? void finish() : ref.current?.scrollToIndex({ index: i + 1 }))} />
        {!last && <Text variant="bodyBold" color={colors.mute} style={{ textAlign: 'center' }} onPress={() => void finish()}>Skip</Text>}
      </View>
    </SafeAreaView>
  );
}
