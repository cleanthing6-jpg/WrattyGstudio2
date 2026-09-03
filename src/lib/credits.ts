export const TIERS: Record<string, { beats: number; covers: number; mixes: number; label: string; price?: number; previewOnly: boolean }> = {
  free: { beats: 0, covers: 1, mixes: 1, label: "Free", previewOnly: true },
  starter: { beats: 5, covers: 3, mixes: 3, label: "Starter", price: 3000, previewOnly: false },
  pro: { beats: 10, covers: 7, mixes: 10, label: "Pro", price: 7000, previewOnly: false },
  studio: { beats: 30, covers: 20, mixes: 30, label: "Studio", price: 14000, previewOnly: false },
};
