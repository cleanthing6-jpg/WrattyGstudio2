"use client";
const tiers = [
  { name: "Free", price: "₦0", beats: "0", covers: "1 (preview)", mixes: "1 (preview)", color: "gray" },
  { name: "Starter", price: "₦3,000", beats: "5", covers: "3", mixes: "3", color: "green" },
  { name: "Pro", price: "₦7,000", beats: "10", covers: "7", mixes: "10", color: "yellow" },
  { name: "Studio", price: "₦14,000", beats: "30", covers: "20", mixes: "30", color: "purple" },
];
export default function Pricing() {
  return (
    <main className="min-h-screen p-8">
      <h1 className="text-4xl font-bold mb-8 text-center">Pricing</h1>
      <div className="grid grid-cols-1 md:grid-cols-4 gap-6 max-w-6xl mx-auto">
        {tiers.map((t) => (
          <div key={t.name} className={`bg-gray-900 p-6 rounded-xl border-2 border-${t.color}-500/30`}>
            <h2 className={`text-2xl font-bold text-${t.color}-400`}>{t.name}</h2>
            <p className="text-3xl font-bold my-4">{t.price}</p>
            <ul className="text-gray-400 space-y-2">
              <li>🎵 Beats: {t.beats}</li>
              <li>🎨 Covers: {t.covers}</li>
              <li>🎚️ Mix: {t.mixes}</li>
            </ul>
            <button className={`w-full mt-6 py-2 rounded-full font-bold bg-${t.color}-500 text-black`}>Select</button>
          </div>
        ))}
      </div>
    </main>
  );
}
