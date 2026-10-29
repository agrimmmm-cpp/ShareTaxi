import { useEffect, useMemo, useRef } from 'react';
import { StyleSheet, View } from 'react-native';
import MapView, { Marker, Polyline } from 'react-native-maps';

import { decodePolyline, LatLng } from '@/lib/polyline';
import { colors, radius } from '@/theme';

import { Text } from './ui';

export interface MapMarker {
  id: string; lat: number; lng: number; title?: string; label?: string; color?: string; kind?: 'pickup' | 'dropoff' | 'driver' | 'demand';
}
export interface MapLine { id: string; encoded?: string; coords?: LatLng[]; color?: string; width?: number; dashed?: boolean }

/** Map with route polylines + numbered markers. Fits the camera to everything drawn. */
export function MapRoute({ lines = [], markers = [], height = 280, rounded = true }: { lines?: MapLine[]; markers?: MapMarker[]; height?: number; rounded?: boolean }) {
  const ref = useRef<MapView>(null);
  const decoded = useMemo(() => lines.map((l) => ({ ...l, pts: l.coords ?? (l.encoded ? decodePolyline(l.encoded) : []) })), [lines]);
  const all = useMemo(
    () => [...decoded.flatMap((l) => l.pts), ...markers.map((m) => ({ latitude: m.lat, longitude: m.lng }))],
    [decoded, markers],
  );
  const fitKey = all.length + ':' + (all[0]?.latitude ?? 0) + ':' + (all.at(-1)?.longitude ?? 0);

  useEffect(() => {
    if (all.length > 1) {
      const t = setTimeout(() => ref.current?.fitToCoordinates(all, { edgePadding: { top: 50, right: 40, bottom: 50, left: 40 }, animated: true }), 250);
      return () => clearTimeout(t);
    }
  }, [fitKey]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <View style={[{ height, overflow: 'hidden' }, rounded && { borderRadius: radius.lg }]}>
      <MapView ref={ref} style={StyleSheet.absoluteFill} initialRegion={{ latitude: 49.18, longitude: -122.7, latitudeDelta: 0.8, longitudeDelta: 0.8 }} toolbarEnabled={false}>
        {decoded.map((l) => l.pts.length > 1 && (
          <Polyline key={l.id} coordinates={l.pts} strokeColor={l.color ?? colors.brand} strokeWidth={l.width ?? 5} lineDashPattern={l.dashed ? [8, 8] : undefined} />
        ))}
        {markers.map((m) => (
          <Marker key={m.id} coordinate={{ latitude: m.lat, longitude: m.lng }} title={m.title} anchor={{ x: 0.5, y: 0.5 }}>
            <MarkerBadge m={m} />
          </Marker>
        ))}
      </MapView>
    </View>
  );
}

function MarkerBadge({ m }: { m: MapMarker }) {
  const bg = m.color ?? (m.kind === 'dropoff' ? colors.ink : m.kind === 'driver' ? colors.driver : m.kind === 'demand' ? colors.warn : colors.brand);
  const square = m.kind === 'dropoff';
  return (
    <View style={{ width: 28, height: 28, borderRadius: square ? 8 : 14, backgroundColor: bg, borderWidth: 2.5, borderColor: colors.white, alignItems: 'center', justifyContent: 'center' }}>
      <Text variant="caption" color={colors.white} style={{ fontWeight: '800' }}>{m.label ?? ''}</Text>
    </View>
  );
}
