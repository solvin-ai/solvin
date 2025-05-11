// pages/settings/index.js

import Link from "next/link";
import Header from "../../components/Header";

export default function Home() {
  return (
    <div className="min-h-screen bg-gray-50">
      <Header
        title="Settings"
        breadcrumbs={[
          { href: "/", label: "Home" },
          { href: "/settings", label: "Settings" }
        ]}
      />

      <main className="max-w-7xl mx-auto py-10 px-4 sm:px-6 lg:px-8">
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-8">
          <Link
            href="/settings/agent-roles"
            className="block p-6 bg-white border border-gray-200 rounded-xl shadow hover:bg-gray-50 transition"
          >
            <h2 className="text-xl font-semibold text-gray-800 mb-2">Agents</h2>
            <p className="text-gray-600">Manage agent roles and their settings.</p>
          </Link>

          <Link
            href="/settings/models"
            className="block p-6 bg-white border border-gray-200 rounded-xl shadow hover:bg-gray-50 transition"
          >
            <h2 className="text-xl font-semibold text-gray-800 mb-2">Models</h2>
            <p className="text-gray-600">Manage LLM providers and available models.</p>
          </Link>

          <Link
            href="/settings/model-providers"
            className="block p-6 bg-white border border-gray-200 rounded-xl shadow hover:bg-gray-50 transition"
          >
            <h2 className="text-xl font-semibold text-gray-800 mb-2">Providers</h2>
            <p className="text-gray-600">Manage LLM/model providers and their info.</p>
          </Link>

          <Link
            href="/settings/tasks"
            className="block p-6 bg-white border border-gray-200 rounded-xl shadow hover:bg-gray-50 transition"
          >
            <h2 className="text-xl font-semibold text-gray-800 mb-2">Tasks</h2>
            <p className="text-gray-600">Manage your task definitions and prompts.</p>
          </Link>

          <Link
            href="/settings/config"
            className="block p-6 bg-white border border-gray-200 rounded-xl shadow hover:bg-gray-50 transition"
          >
            <h2 className="text-xl font-semibold text-gray-800 mb-2">Config</h2>
            <p className="text-gray-600">Control global config values.</p>
          </Link>

          <Link
            href="/settings/templates"
            className="block p-6 bg-white border border-gray-200 rounded-xl shadow hover:bg-gray-50 transition"
          >
            <h2 className="text-xl font-semibold text-gray-800 mb-2">Templates</h2>
            <p className="text-gray-600">Import/export YAML snapshots of your config.</p>
          </Link>
        </div>
      </main>
    </div>
  );
}
