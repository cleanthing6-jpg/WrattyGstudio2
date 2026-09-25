const fr = await withTimeout(fetch("/api/vocal-fx", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({
    preset: "afrobeats",
    url: st.url,
    bpm: st.bpm,
    style: px,
    preview: true,
  }),
  if (fr.ok && fj.url) url = fj.url;
  else console.warn("[vocal-fx]", fj.error || fr.status);
} catch (e) {
  console.warn("[vocal-fx] skipped:", e);
}
