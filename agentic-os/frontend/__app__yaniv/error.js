// app/error.js

"use client";

import { useEffect } from "react";

export default function GlobalError({ error, reset }) {
  useEffect(() => {
    // Log the error to your analytics/reporting service if desired
    console.error("Error caught by App Router error boundary:", error);
  }, [error]);

  return (
    <html>
      <body>
        <div className="min-h-screen flex flex-col justify-center items-center bg-red-50">
          <h2 className="text-4xl font-bold text-red-600 mb-4">Something went wrong!</h2>
          <p className="mb-8 text-lg text-red-700">{error.message}</p>
          <button
            onClick={() => reset()}
            className="px-6 py-2 bg-red-600 text-white rounded mt-4 hover:bg-red-700 transition"
          >
            Try again
          </button>
        </div>
      </body>
    </html>
  );
}
