import { create } from 'zustand';

/** The "Where are you going?" form on Home, shared with Explore and the request form. */
interface Draft {
  origin: string;
  destination: string;
  departure: Date;
  flexibleMinutes: number;
  passengers: number;
  set: (patch: Partial<Omit<Draft, 'set' | 'reset'>>) => void;
  reset: () => void;
}

function defaultDeparture(): Date {
  const d = new Date(Date.now() + 24 * 3600_000);
  d.setHours(9, 0, 0, 0);
  return d;
}

export const useDraft = create<Draft>((set) => ({
  origin: '',
  destination: '',
  departure: defaultDeparture(),
  flexibleMinutes: 30,
  passengers: 1,
  set: (patch) => set(patch),
  reset: () => set({ origin: '', destination: '', departure: defaultDeparture(), flexibleMinutes: 30, passengers: 1 }),
}));
