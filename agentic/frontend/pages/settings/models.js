// pages/settings/models.js

import { useState, useEffect } from "react";
import Header from "../../components/Header";

export default function ModelsPage() {
  const [models, setModels] = useState([]);
  const [providers, setProviders] = useState([]);
  const [form, setForm] = useState({
    id: null,
    provider_id: "",
    model_name: "",
    extra_info: "",
    supports_reasoning: 1,
  });
  const [showForm, setShowForm] = useState(false);
  const [editing, setEditing] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    fetchModels();
    fetchProviders();
  }, []);

  const fetchModels = async () => {
    const res = await fetch("/api/models?withProviders=1");
    const data = await res.json();
    setModels(data.models || []);
  };

  const fetchProviders = async () => {
    const res = await fetch("/api/model-providers");
    const data = await res.json();
    setProviders(data.providers || []);
  };

  const openForm = (model = null) => {
    if (model) {
      setEditing(true);
      setForm({
        id: model.id,
        provider_id: model.provider_id,
        model_name: model.model_name,
        extra_info: model.extra_info || "",
        supports_reasoning: typeof model.supports_reasoning === "undefined" ? 1 : model.supports_reasoning,
      });
    } else {
      setEditing(false);
      setForm({
        id: null,
        provider_id: "",
        model_name: "",
        extra_info: "",
        supports_reasoning: 1,
      });
    }
    setShowForm(true);
    setError("");
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");
    const url = "/api/models";
    const method = editing ? "PUT" : "POST";
    try {
      const res = await fetch(url, {
        method,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ...form,
          provider_id: parseInt(form.provider_id, 10),
          supports_reasoning: form.supports_reasoning ? 1 : 0,
        }),
      });
      if (!res.ok) {
        const d = await res.json();
        throw new Error(d.error || "Error saving model");
      }
      setShowForm(false);
      fetchModels();
    } catch (err) {
      setError(err.message);
    }
  };

  const handleDelete = async (id) => {
    if (!window.confirm("Delete this model?")) return;
    try {
      const res = await fetch(`/api/models?id=${id}`, { method: "DELETE" });
      if (!res.ok) throw new Error("Error deleting model");
      fetchModels();
    } catch (err) {
      setError(err.message);
    }
  };

  return (
    <div className="min-h-screen bg-gray-50">
      <Header
        title="Manage Models"
        breadcrumbs={[
          { href: "/", label: "Home" },
          { href: "/settings", label: "Settings" },
          { href: "/settings/models", label: "Models" },
        ]}
      />
      <main className="max-w-4xl mx-auto py-10 px-4 sm:px-6 lg:px-8">
        {!showForm && (
        <button
          className="mb-8 bg-green-600 text-white px-5 py-2 rounded hover:bg-green-700 transition"
          onClick={() => openForm()}
        >
          + Add Model
        </button>
        )}

        {showForm && (
          <div className="bg-white p-6 rounded-xl shadow-md mb-10">
            <h2 className="text-xl font-semibold mb-4">{editing ? "Edit" : "Add"} Model</h2>
            <form onSubmit={handleSubmit} className="space-y-4">
              <div>
                <label className="block font-medium mb-1">Provider</label>
                <div className="flex items-center">
                  <select
                    required
                    className="border rounded px-3 py-2 w-full"
                    value={form.provider_id}
                    onChange={e => setForm({ ...form, provider_id: e.target.value })}
                  >
                    <option value="">Select provider...</option>
                    {providers.map(p => (
                      <option key={p.id} value={p.id}>
                        {p.display_name}
                      </option>
                    ))}
                  </select>
                  <button
                    type="button"
                    className="ml-2 bg-blue-600 hover:bg-blue-700 text-white px-3 py-1 rounded"
                    onClick={() => window.open("/settings/model-providers", "_blank")}
                  >
                    + New Provider
                  </button>
                </div>
              </div>
              <div>
                <label className="block font-medium mb-1">Model Name</label>
                <input
                  className="border rounded px-3 py-2 w-full"
                  value={form.model_name}
                  onChange={e => setForm({ ...form, model_name: e.target.value })}
                  required
                  placeholder="e.g. gpt-4, gpt-3.5-turbo"
                />
              </div>
              <div>
                <label className="block font-medium mb-1">Extra Info</label>
                <input
                  className="border rounded px-3 py-2 w-full"
                  value={form.extra_info}
                  onChange={e => setForm({ ...form, extra_info: e.target.value })}
                  placeholder="Optional JSON or notes"
                />
              </div>
              <div>
                <label className="inline-flex items-center space-x-2">
                  <input
                    type="checkbox"
                    className="form-checkbox"
                    checked={!!form.supports_reasoning}
                    onChange={e =>
                      setForm({
                        ...form,
                        supports_reasoning: e.target.checked ? 1 : 0
                      })
                    }
                  />
                  <span>Reasoning</span>
                </label>
              </div>
              {error && <div className="text-red-600">{error}</div>}
              <div className="space-x-4 mt-4">
                <button
                  type="submit"
                  className="bg-blue-600 hover:bg-blue-700 text-white px-5 py-2 rounded transition"
                >
                  {editing ? "Update Model" : "Add Model"}
                </button>
                <button
                  type="button"
                  className="bg-gray-600 hover:bg-gray-700 text-white px-5 py-2 rounded transition"
                  onClick={() => setShowForm(false)}
                >
                  Cancel
                </button>
              </div>
            </form>
          </div>
        )}

        <div className="bg-white p-6 rounded-xl shadow">
          <h2 className="text-xl font-semibold mb-4">Existing Models</h2>
          <table className="min-w-full border">
            <thead>
              <tr>
                <th className="py-1 px-2 text-left">Provider</th>
                <th className="py-1 px-2 text-left">Model Name</th>
                <th className="py-1 px-2 text-left">Extra Info</th>
                <th className="py-1 px-2 text-left">Reasoning</th>
                <th className="py-1 px-2"></th>
              </tr>
            </thead>
            <tbody>
              {models.map(m => (
                <tr key={m.id}>
                  <td className="py-1 px-2">{m.provider_display_name || m.provider_name || ""}</td>
                  <td className="py-1 px-2">{m.model_name}</td>
                  <td className="py-1 px-2">{m.extra_info}</td>
                  <td className="py-1 px-2">{m.supports_reasoning ? "Yes" : "No"}</td>
                  <td className="py-1 px-2">
                    <button
                      className="bg-green-500 text-white px-3 py-1 rounded hover:bg-green-600"
                      onClick={() => openForm(m)}
                    >
                      Edit
                    </button>
                    <button
                      className="ml-2 bg-red-600 text-white px-3 py-1 rounded hover:bg-red-700"
                      onClick={() => handleDelete(m.id)}
                    >
                      Delete
                    </button>
                  </td>
                </tr>
              ))}
              {models.length === 0 && (
                <tr>
                  <td colSpan={5} className="text-gray-500 text-center py-4">
                    No models found.
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
