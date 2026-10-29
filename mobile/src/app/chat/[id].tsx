import { Ionicons } from '@expo/vector-icons';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { useEffect, useRef, useState } from 'react';
import { FlatList, KeyboardAvoidingView, Platform, Pressable, ScrollView, TextInput, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { useMessages, useQuickMessages, useRideSocket, useSendMessage } from '@/api/hooks';
import { Chip, ErrorBanner, Row, Text } from '@/components/ui';
import { timeLabel } from '@/lib/format';
import { colors, radius, space } from '@/theme';

export default function Chat() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const rideId = Number(id);
  const router = useRouter();
  const messages = useMessages(rideId);
  const quick = useQuickMessages();
  const send = useSendMessage(rideId);
  const [text, setText] = useState('');
  const list = useRef<FlatList>(null);
  useRideSocket(rideId);
  useEffect(() => { setTimeout(() => list.current?.scrollToEnd({ animated: true }), 100); }, [messages.data?.length]);

  const submit = (body: string, kind: 'text' | 'quick' = 'text') => {
    if (!body.trim()) return;
    send.mutate({ body: body.trim(), kind });
    setText('');
  };

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: colors.bg }} edges={['top', 'bottom']}>
      <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
        <Row style={{ padding: space.lg, justifyContent: 'space-between' }}>
          <Pressable onPress={() => router.back()}><Ionicons name="chevron-back" size={26} color={colors.ink} /></Pressable>
          <View style={{ alignItems: 'center' }}><Text variant="h2">Ride chat</Text><Text variant="caption" color={colors.mute}>Phone numbers are hidden</Text></View>
          <View style={{ width: 26 }} />
        </Row>
        <ErrorBanner error={send.error} />
        <FlatList
          ref={list} data={messages.data ?? []} keyExtractor={(m) => String(m.id)} contentContainerStyle={{ padding: space.lg, gap: 8 }}
          renderItem={({ item: m }) => m.kind === 'system' ? (
            <Text variant="caption" color={colors.mute} style={{ textAlign: 'center', marginVertical: 6 }}>{m.body}</Text>
          ) : (
            <View style={{ alignSelf: m.mine ? 'flex-end' : 'flex-start', maxWidth: '82%' }}>
              {!m.mine && <Text variant="caption" color={colors.mute} style={{ marginLeft: 6 }}>{m.sender_label}</Text>}
              <View style={{ backgroundColor: m.mine ? colors.brand : colors.card, borderRadius: radius.lg, paddingHorizontal: 14, paddingVertical: 10 }}>
                <Text color={m.mine ? colors.white : colors.ink}>{m.body}</Text>
              </View>
              <Text variant="caption" color={colors.mute} style={{ alignSelf: m.mine ? 'flex-end' : 'flex-start', marginHorizontal: 6 }}>{timeLabel(m.created_at)}</Text>
            </View>
          )}
        />
        <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ flexGrow: 0, paddingVertical: 8 }} contentContainerStyle={{ paddingHorizontal: space.lg, gap: 8 }}>
          {(quick.data ?? []).map((q) => <Chip key={q} label={q} onPress={() => submit(q, 'quick')} />)}
        </ScrollView>
        <Row style={{ padding: space.md, backgroundColor: colors.card }} gap={8}>
          <TextInput value={text} onChangeText={setText} placeholder="Message the group" placeholderTextColor={colors.mute} onSubmitEditing={() => submit(text)}
            style={{ flex: 1, minHeight: 44, borderRadius: 22, backgroundColor: colors.bg, paddingHorizontal: 16, fontSize: 16 }} />
          <Pressable onPress={() => submit(text)} style={{ width: 44, height: 44, borderRadius: 22, backgroundColor: colors.brand, alignItems: 'center', justifyContent: 'center' }}>
            <Ionicons name="send" size={18} color={colors.white} />
          </Pressable>
        </Row>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}
