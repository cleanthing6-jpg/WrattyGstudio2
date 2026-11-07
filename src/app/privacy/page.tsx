export const metadata = { title: "Privacy Policy - WrattyGstudio" };

export default function Privacy() {
  return (
    <main className="mx-auto max-w-2xl px-4 py-10 text-sm leading-relaxed text-gray-700">
      <h1 className="mb-4 text-2xl font-bold text-gray-900">Privacy Policy</h1>
      <p className="mb-4">Last updated: {new Date().toISOString().slice(0, 10)}</p>
      <h2 className="mb-2 mt-6 text-lg font-semibold text-gray-900">What we collect</h2>
      <p className="mb-3">Your account email, your audio uploads, and your usage counters (mixes, masters, covers). Payments are processed by Paystack - we never see or store your card details.</p>
      <h2 className="mb-2 mt-6 text-lg font-semibold text-gray-900">How we use it</h2>
      <p className="mb-3">To run your renders, enforce plan limits, and email you when a render finishes. We do not sell your data.</p>
      <h2 className="mb-2 mt-6 text-lg font-semibold text-gray-900">Your audio</h2>
      <p className="mb-3">Uploads are stored so we can render them and kept while your account is active. Finished renders stay available to download for 30 days - keep your own copy. Renders are yours - you keep all rights to your music.</p>
      <h2 className="mb-2 mt-6 text-lg font-semibold text-gray-900">Contact</h2>
      <p>Questions or deletion requests: wrattyg@gmail.com</p>
    </main>
  );
}
