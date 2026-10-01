export const metadata = { title: "Support - WrattyGstudio" };

export default function Support() {
  return (
    <main className="mx-auto max-w-2xl px-4 py-10 text-sm leading-relaxed text-gray-700">
      <h1 className="mb-4 text-2xl font-bold text-gray-900">Support</h1>
      <p className="mb-3">Email <strong>your.real.address@gmail.com</strong> - include your account email and, for payment issues, your Paystack reference.</p>
      <h2 className="mb-2 mt-6 text-lg font-semibold text-gray-900">Common fixes</h2>
      <ul className="list-disc pl-5">
        <li className="mb-1">Plan not active after paying? Reply with your reference - we activate it manually.</li>
        <li className="mb-1">Render stuck? A stuck job is reaped automatically; just submit again.</li>
        <li className="mb-1">Render status updates live on the page - refresh if it looks stuck.</li>
      </ul>
    </main>
  );
}
