// app/not-found.js

export default function NotFound() {
  return (
    <html>
      <body>
        <div className="min-h-screen flex flex-col items-center justify-center bg-gray-50">
          <h1 className="text-5xl font-bold text-gray-800 mb-4">404 - Page Not Found</h1>
          <p className="text-lg text-gray-600 mb-8">
            Sorry, the page you&apos;re looking for does not exist.
          </p>
          <a
            href="/"
            className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 transition"
          >
            Return to Home
          </a>
        </div>
      </body>
    </html>
  );
}
