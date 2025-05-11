// components/Header.js  

import { useRouter } from "next/router";
import Link from "next/link";

export default function Header({ title, breadcrumbs = [] }) {
  const router = useRouter();
  return (
    <header className="bg-white shadow">
      <div className="max-w-7xl mx-auto py-4 px-4 sm:px-6 lg:px-8">
        {/* Dynamic title */}
        <h1 className="text-3xl font-extrabold text-gray-900">{title}</h1>
        {/* Breadcrumbs */}
        {breadcrumbs.length > 0 && (
          <nav className="mt-2 text-sm text-gray-500">
            <ol className="list-reset flex">
              {breadcrumbs.map((crumb, index) => (
                <li key={crumb.href} className="flex items-center">
                  <Link href={crumb.href} className="hover:underline">
                    {crumb.label}
                  </Link>
                  {index < breadcrumbs.length - 1 && (
                    <span className="mx-2">/</span>
                  )}
                </li>
              ))}
            </ol>
          </nav>
        )}
        {/* Single line of navigation: Back and Home */}
        <div className="mt-2 flex justify-between items-center">
          <button
            type="button"
            onClick={() => router.back()}
            className="text-blue-600 hover:underline"
          >
            &larr; Back
          </button>
          <Link href="/" className="text-blue-600 hover:underline">
            Home
          </Link>
        </div>
      </div>
    </header>
);

}
