"use client";

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <div className="mx-auto max-w-md p-8 text-center">
      <h1 className="text-lg font-bold">Something went wrong</h1>
      <p className="mt-2 text-sm text-gray-600">
        Please try again. If it keeps happening, message us on WhatsApp or email
        wrattyg@gmail.com.
      </p>
      <button
        onClick={() => reset()}
        className="mt-4 rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white"
      >
        Try again
      </button>
    </div>
  );
}
