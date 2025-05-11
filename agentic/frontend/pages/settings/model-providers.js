// pages/settings/model-providers.js

import { useState, useEffect } from "react";
import Header from "../../components/Header";

export default function ModelProvidersPage() {
  const [providers, setProviders] = useState([]);
  const [form, setForm] = useState({
    id: null,
    provider_name: "",
    display_name: "",
    extra_info: "",
  });
  const [showForm, setShowForm] = useState(false);
  const [editing, setEditing] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    fetchProviders();
  }, []);

  const fetchProviders = async () => {
    const res = await fetch("/api/model-providers");
    const data = await res.json();
    setProviders(data.providers || []);
  };

  const openForm = (provider = null) => {
    if (provider) {
      setEditing(true);
      setForm({
        id: provider.id,
        provider_name: provider.provider_name,
        display_name: provider.display_name,
        extra_info: provider.extra_info || "",
      });
    } else {
      setEditing(false);
      setForm({
        id: null,
        provider_name: "",
        display_name: "",
        extra_info: "",
      });
    }
    setShowForm(true);
    setError("");
  };

  // Track if user has manually changed "display_name" during creation
  const [displayTouched, setDisplayTouched] = useState(false);

  const handleProviderNameChange = (e) => {
    const val = e.target.value;
    setForm((f) => ({
      ...f,
      provider_name: val,
      display_name: (!editing && !displayTouched) ? val : f.display_name,
    }));
  };

  const handleDisplayNameChange = (e) => {
    setDisplayTouched(true);
    setForm((f) => ({
      ...f,
      display_name: e.target.value,
    }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");
    const url = "/api/model-providers";
    const method = editing ? "PUT" : "POST";
    const submission = { ...form };
    if (!submission.display_name || submission.display_name.trim() === "") {
      submission.display_name = submission.provider_name;
    }
    try {
      const res = await fetch(url, {
        method,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(submission),
      });
      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.error || "Error saving provider");
      }
      setShowForm(false);
      setDisplayTouched(false);
      fetchProviders();
    } catch (err) {
      setError(err.message);
    }
  };

  const handleDelete = async (id) => {
    if (!window.confirm("Delete this provider?")) return;
    try {
      const res = await fetch(`/api/model-providers?id=${id}`, { method: "DELETE" });
      if (!res.ok) throw new Error("Error deleting provider");
      fetchProviders();
    } catch (err) {
      setError(err.message);
    }
  };

  return (
    <div className="min-h-screen bg-gray-50">
      <Header
        title="Manage Model Providers"
        breadcrumbs={[
          { href: "/", label: "Home" },
          { href: "/settings", label: "Settings" },
          { href: "/settings/model-providers", label: "Model Providers" },
        ]}
      />

      <main className="max-w-2xl mx-auto py-10 px-4 sm:px-6 lg:px-8">
        {!showForm && (
        <button
          className="mb-8 bg-green-600 text-white px-5 py-2 rounded hover:bg-green-700 transition"
          onClick={() => openForm()}
        >
          + Add Provider
        </button>
        )}

        {showForm && (
          <div className="bg-white p-6 rounded-xl shadow-md mb-10">
            <h2 className="text-xl font-semibold mb-4">{editing ? "Edit" : "Add"} Provider</h2>
            <form onSubmit={handleSubmit} className="space-y-4">
              <div>
                <label className="block font-medium">Provider Name</label>
                <input
                  className="border rounded px-3 py-2 w-full"
                  value={form.provider_name}
                  onChange={handleProviderNameChange}
                  required
                  disabled={editing}
                  placeholder="e.g. openai"
                />
              </div>
              <div>
                <label className="block font-medium">Display Name</label>
                <input
                  className="border rounded px-3 py-2 w-full"
                  value={form.display_name}
                  onChange={handleDisplayNameChange}
                  required
                  placeholder="e.g. OpenAI"
                />
              </div>
              <div>
                <label className="block font-medium">Extra Info</label>
                <input
                  className="border rounded px-3 py-2 w-full"
                  value={form.extra_info}
                  onChange={(e) => setForm({ ...form, extra_info: e.target.value })}
                  placeholder="(Optional) notes or JSON"
                />
              </div>
              {error && <div className="text-red-600">{error}</div>}
              <div className="space-x-4 mt-4">
                <button
                  type="submit"
                  className="bg-blue-600 hover:bg-blue-700 text-white px-5 py-2 rounded transition"
                >
                  {editing ? "Update" : "Add"}
                </button>
                <button
                  type="button"
                  className="bg-gray-600 hover:bg-gray-700 text-white px-5 py-2 rounded transition"
                  onClick={() => {
                    setShowForm(false);
                    setDisplayTouched(false);
                  }}
                >
                  Cancel
                </button>
              </div>
            </form>
          </div>
        )}

        <div className="bg-white p-6 rounded-xl shadow">
          <h2 className="text-xl font-semibold mb-4">Existing Providers</h2>
          <table className="min-w-full border">
            <thead>
              <tr>
                <th className="py-1 px-2 text-left">Provider Name</th>
                <th className="py-1 px-2 text-left">Display Name</th>
                <th className="py-1 px-2 text-left">Extra Info</th>
                <th className="py-1 px-2"></th>
              </tr>
            </thead>
            <tbody>
              {providers.map((p) => (
                <tr key={p.id}>
                  <td className="py-1 px-2">{p.provider_name}</td>
                  <td className="py-1 px-2">{p.display_name}</td>
                  <td className="py-1 px-2">{p.extra_info}</td>
                  <td className="py-1 px-2">
                    <button
                      className="bg-green-500 text-white px-3 py-1 rounded hover:bg-green-600"
                      onClick={() => {
                        openForm(p);
                        setDisplayTouched(false);
                      }}
                    >
                      Edit
                    </button>
                    <button
                      className="ml-2 bg-red-600 text-white px-3 py-1 rounded hover:bg-red-700"
                      onClick={() => handleDelete(p.id)}
                    >
                      Delete
                    </button>
                  </td>
                </tr>
              ))}
              {providers.length === 0 && (
                <tr>
                  <td colSpan={4} className="text-gray-500 text-center py-4">
                    No providers found.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </main>
    </div>
  );
}
