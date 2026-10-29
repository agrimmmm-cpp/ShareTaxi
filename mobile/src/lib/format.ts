/** The API returns UTC datetimes without a zone suffix; always parse them as UTC. */
export function parseDate(iso: string): Date {
  return new Date(/Z$|[+-]\d\d:\d\d$/.test(iso) ? iso : iso + 'Z');
}

export const money = (n: number | null | undefined): string => (n == null ? '–' : `$${n.toFixed(n % 1 === 0 ? 0 : 2)}`);
export const money2 = (n: number | null | undefined): string => (n == null ? '–' : `$${n.toFixed(2)}`);

export function timeLabel(iso: string): string {
  return parseDate(iso).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
}

export function dayLabel(iso: string | Date): string {
  const d = typeof iso === 'string' ? parseDate(iso) : iso;
  const today = new Date();
  const diff = Math.round((startOfDay(d).getTime() - startOfDay(today).getTime()) / 86_400_000);
  if (diff === 0) return 'Today';
  if (diff === 1) return 'Tomorrow';
  return d.toLocaleDateString([], { weekday: 'short', month: 'short', day: 'numeric' });
}

export const startOfDay = (d: Date): Date => new Date(d.getFullYear(), d.getMonth(), d.getDate());

export function windowLabel(from: string | null | undefined, to: string | null | undefined): string {
  if (!from || !to) return '';
  return `${timeLabel(from)} – ${timeLabel(to)}`;
}

export function duration(min: number): string {
  const h = Math.floor(min / 60);
  const m = Math.round(min % 60);
  return h ? `${h}h ${m.toString().padStart(2, '0')}m` : `${m} min`;
}

export const pct = (n: number | null | undefined): string => (n == null ? '–' : `${Math.round(n)}%`);
