// pages/settings/agent-roles.js

import { useState, useEffect } from "react";
import { useRouter } from "next/router";
import Header from "../../components/Header";

// helper to turn snake_case into "Human Readable"
function humanizeSnakeCase(name) {
  return name
    .split("_")
    .map(word => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}

// the tool we always want pre-selected (in snake_case for API/DB)
const DEFAULT_TOOL = "set_work_completed";

// helper to inject DEFAULT_TOOL if missing
function ensureDefaultTool(arr = []) {
  const tools = Array.isArray(arr) ? [...arr] : [];
  if (!tools.includes(DEFAULT_TOOL)) {
    tools.push(DEFAULT_TOOL);
  }
  return tools;
}

export default function AgentTypesPage() {
  const router = useRouter();

  // Initial form data template
  const initialFormData = {
    agent_role: "",
    agent_description: "",
    default_developer_prompt: "",
    default_user_prompt: "",
    model_id: "",
    reasoning_level: "medium",
    tool_choice: "auto",
    // start with our default tool already in the selected list
    allowed_tools: [DEFAULT_TOOL],
  };

  // State
  const [agentTypes, setAgentTypes] = useState([]);
  const [models, setModels] = useState([]);
  const [availableTools, setAvailableTools] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [showForm, setShowForm] = useState(false);
  const [editingAgent, setEditingAgent] = useState(null);
  const [formData, setFormData] = useState(initialFormData);

  // Dual-list selections
  const [leftSelected, setLeftSelected] = useState([]);
  const [rightSelected, setRightSelected] = useState([]);

  // Fetch agent roles list
  useEffect(() => {
    fetchAgentTypes();
  }, []);

  async function fetchAgentTypes() {
    setLoading(true);
    setError("");
    try {
      const res = await fetch("/api/agent-roles");
      if (!res.ok) throw new Error("Failed to load agent roles");
      const { agentTypes: data } = await res.json();
      setAgentTypes(data || []);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  // Fetch available tools
  useEffect(() => {
    fetch("/api/tools")
      .then((r) => r.json())
      .then((d) => setAvailableTools(d.tools || []))
      .catch((e) => console.error("Error fetching tools:", e));
  }, []);

  // Fetch models
  useEffect(() => {
    fetch("/api/models?withProviders=1")
      .then((r) => r.json())
      .then((d) => setModels(d.models || []))
      .catch((e) => console.error("Error fetching models:", e));
  }, []);

  // Sync form visibility with query param (back button support)
  useEffect(() => {
    // when ?form is removed, hide form & reset
    if (!router.query.form) {
      setShowForm(false);
      setEditingAgent(null);
      setFormData(initialFormData);
    }
    // we rely on openAddForm/openEditForm to set showForm=true
  }, [router.query.form]);

  // Open Add Form
  function openAddForm() {
    setEditingAgent(null);
    setFormData({ ...initialFormData });
    setLeftSelected([]);
    setRightSelected([]);
    setError("");
    setShowForm(true);
    router.push(
      { pathname: "/settings/agent-roles", query: { form: "add" } },
      undefined,
      { shallow: true }
    );
  }

  // Open Edit Form (fetch full agent details)
  async function openEditForm(agentSummary) {
    setError("");
    setLoading(true);
    try {
      const res = await fetch(
        `/api/agent-roles?agent_role=${encodeURIComponent(
          agentSummary.agent_role
        )}`
      );
      if (!res.ok) throw new Error("Failed to load agent details");
      const { agent } = await res.json();

      // parse existing tools
      let parsedTools = Array.isArray(agent.allowed_tools)
        ? [...agent.allowed_tools]
        : [];
      try {
        if (!parsedTools.length) {
          parsedTools = JSON.parse(agent.allowed_tools || "[]");
        }
      } catch {}
      parsedTools = ensureDefaultTool(parsedTools);

      setEditingAgent(agent);
      setFormData({
        agent_role: agent.agent_role,
        agent_description: agent.agent_description || "",
        default_developer_prompt:
          agent.default_developer_prompt || "",
        default_user_prompt: agent.default_user_prompt || "",
        model_id: agent.model_id || "",
        reasoning_level: agent.reasoning_level || "medium",
        tool_choice: agent.tool_choice || "auto",
        allowed_tools: parsedTools,
      });
      setLeftSelected([]);
      setRightSelected([]);
      setShowForm(true);
      router.push(
        {
          pathname: "/settings/agent-roles",
          query: { form: "edit", agent_role: agentSummary.agent_role },
        },
        undefined,
        { shallow: true }
      );
    } catch (e) {
      console.error("Error fetching agent details:", e);
      setError("Error loading agent details.");
    } finally {
      setLoading(false);
    }
  }

  // Dual-list helpers
  const availableList = availableTools.filter(
    (t) => !formData.allowed_tools.includes(t)
  );

  function toggleLeft(tool) {
    setLeftSelected((s) =>
      s.includes(tool) ? s.filter((x) => x !== tool) : [...s, tool]
    );
  }
  function toggleRight(tool) {
    setRightSelected((s) =>
      s.includes(tool) ? s.filter((x) => x !== tool) : [...s, tool]
    );
  }
  function addSelected() {
    setFormData((f) => ({
      ...f,
      allowed_tools: Array.from(
        new Set([...f.allowed_tools, ...leftSelected])
      ),
    }));
    setLeftSelected([]);
  }
  function removeSelected() {
    setFormData((f) => ({
      ...f,
      allowed_tools: f.allowed_tools.filter(
        (t) => !rightSelected.includes(t)
      ),
    }));
    setRightSelected([]);
  }
  function selectAll() {
    setFormData((f) => ({ ...f, allowed_tools: [...availableTools] }));
  }
  function clearAll() {
    setFormData((f) => ({ ...f, allowed_tools: [] }));
  }

  // Handle form submission
  async function handleFormSubmit(e) {
    e.preventDefault();
    setError("");
    const url = "/api/agent-roles";
    const method = editingAgent ? "PUT" : "POST";
    try {
      const res = await fetch(url, {
        method,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(formData),
      });
      const result = await res.json();
      if (!res.ok) throw new Error(result.error || "Error saving agent role");
      await fetchAgentTypes();
      // after save, go back to list
      router.push(
        { pathname: "/settings/agent-roles" },
        undefined,
        { shallow: true }
      );
    } catch (e) {
      setError(e.message);
    }
  }

  // Handle delete
  async function handleDelete(agent_role) {
    if (!confirm("Delete this agent role?")) return;
    setError("");
    try {
      const res = await fetch(
        `/api/agent-roles?agent_role=${encodeURIComponent(agent_role)}`,
        { method: "DELETE" }
      );
      if (!res.ok) {
        const d = await res.json();
        throw new Error(d.error || "Error deleting agent role");
      }
      await fetchAgentTypes();
    } catch (e) {
      setError(e.message);
    }
  }

  // Cancel / hide form
  function handleCancel() {
    router.push(
      { pathname: "/settings/agent-roles" },
      undefined,
      { shallow: true }
    );
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <Header
        title="Manage Agent Roles"
        breadcrumbs={[
          { href: "/", label: "Home" },
          { href: "/settings", label: "Settings" },
          { href: "/settings/agent-roles", label: "Agent Roles" },
        ]}
      />

      <main className="max-w-7xl mx-auto py-10 px-4 sm:px-6 lg:px-8">
        {!showForm && (
          <button
            onClick={openAddForm}
            className="mb-6 bg-green-600 hover:bg-green-700 text-white px-4 py-2 rounded"
          >
            + Add Agent Role
          </button>
        )}

        {showForm && (
          <div className="bg-white shadow rounded-lg p-6 mb-10">
            <h2 className="text-xl font-semibold mb-4">
              {editingAgent ? "Edit Agent Role" : "Add Agent Role"}
            </h2>
            <form onSubmit={handleFormSubmit} className="space-y-6">
              {/* Type & Description */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div>
                  <label className="block text-sm font-medium text-gray-700">
                    Agent Role
                  </label>
                  <input
                    required
                    className="mt-1 block w-full border-gray-300 rounded-md shadow-sm"
                    value={formData.agent_role}
                    onChange={(e) =>
                      setFormData({
                        ...formData,
                        agent_role: e.target.value,
                      })
                    }
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700">
                    Description
                  </label>
                  <input
                    className="mt-1 block w-full border-gray-300 rounded-md shadow-sm"
                    value={formData.agent_description}
                    onChange={(e) =>
                      setFormData({
                        ...formData,
                        agent_description: e.target.value,
                      })
                    }
                  />
                </div>
              </div>

              {/* Prompts */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div>
                  <label className="block text-sm font-medium text-gray-700">
                    Default Developer Prompt
                  </label>
                  <textarea
                    className="mt-1 block w-full border-gray-300 rounded-md shadow-sm h-32"
                    value={formData.default_developer_prompt}
                    onChange={(e) =>
                      setFormData({
                        ...formData,
                        default_developer_prompt: e.target.value,
                      })
                    }
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700">
                    Default User Prompt
                  </label>
                  <textarea
                    className="mt-1 block w-full border-gray-300 rounded-md shadow-sm h-32"
                    value={formData.default_user_prompt}
                    onChange={(e) =>
                      setFormData({
                        ...formData,
                        default_user_prompt: e.target.value,
                      })
                    }
                  />
                </div>
              </div>

              {/* Model / Reasoning / Tool Choice */}
              <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                <div>
                  <label className="block text-sm font-medium text-gray-700">
                    Model
                  </label>
                  <select
                    className="mt-1 block w-full border-gray-300 rounded-md shadow-sm"
                    value={formData.model_id}
                    onChange={(e) =>
                      setFormData({
                        ...formData,
                        model_id: e.target.value,
                      })
                    }
                  >
                    <option value="">— Select Model —</option>
                    {models.map((m) => (
                      <option key={m.id} value={m.id}>
                        {m.provider_display_name} / {m.model_name}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700">
                    Reasoning Level
                  </label>
                  <select
                    className="mt-1 block w-full border-gray-300 rounded-md shadow-sm"
                    value={formData.reasoning_level}
                    onChange={(e) =>
                      setFormData({
                        ...formData,
                        reasoning_level: e.target.value,
                      })
                    }
                  >
                    <option value="low">Low</option>
                    <option value="medium">Medium</option>
                    <option value="high">High</option>
                  </select>
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700">
                    Tool Choice
                  </label>
                  <select
                    className="mt-1 block w-full border-gray-300 rounded-md shadow-sm"
                    value={formData.tool_choice}
                    onChange={(e) => {
                      const tc = e.target.value;
                      setFormData((f) => ({
                        ...f,
                        tool_choice: tc,
                        allowed_tools:
                          tc === "none" ? [] : f.allowed_tools,
                      }));
                    }}
                  >
                    <option value="none">None</option>
                    <option value="auto">Auto</option>
                    <option value="required">Required</option>
                  </select>
                </div>
              </div>

              {/* Allowed Tools */}
              <div
                className={`mt-6 p-4 border border-gray-200 rounded-lg ${
                  formData.tool_choice === "none"
                    ? "opacity-50 pointer-events-none"
                    : ""
                }`}
              >
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Allowed Tools
                </label>
                <div className="flex gap-4">
                  {/* Available */}
                  <ul className="flex-1 border border-gray-300 rounded-md p-2 max-h-48 overflow-auto">
                    {availableList.map((t) => (
                      <li
                        key={t}
                        onClick={() => toggleLeft(t)}
                        className={`cursor-pointer px-2 py-1 ${
                          leftSelected.includes(t)
                            ? "bg-blue-100"
                            : "hover:bg-gray-100"
                        } rounded`}
                      >
                        {humanizeSnakeCase(t)}
                      </li>
                    ))}
                    {availableList.length === 0 && (
                      <li className="text-gray-500">
                        No tools available
                      </li>
                    )}
                  </ul>

                  {/* Controls */}
                  <div className="flex flex-col justify-center gap-2">
                    <button
                      type="button"
                      onClick={addSelected}
                      className="px-3 py-1 bg-blue-600 text-white rounded hover:bg-blue-700"
                    >
                      &gt;
                    </button>
                    <button
                      type="button"
                      onClick={removeSelected}
                      className="px-3 py-1 bg-blue-600 text-white rounded hover:bg-blue-700"
                    >
                      &lt;
                    </button>
                    <button
                      type="button"
                      onClick={selectAll}
                      className="px-3 py-1 bg-green-600 text-white rounded hover:bg-green-700"
                    >
                      All
                    </button>
                    <button
                      type="button"
                      onClick={clearAll}
                      className="px-3 py-1 bg-red-600 text-white rounded hover:bg-red-700"
                    >
                      Clear
                    </button>
                  </div>

                  {/* Selected */}
                  <ul className="flex-1 border border-gray-300 rounded-md p-2 max-h-48 overflow-auto">
                    {formData.allowed_tools.map((t) => (
                      <li
                        key={t}
                        onClick={() => toggleRight(t)}
                        className={`cursor-pointer px-2 py-1 ${
                          rightSelected.includes(t)
                            ? "bg-blue-100"
                            : "hover:bg-gray-100"
                        } rounded`}
                      >
                        {humanizeSnakeCase(t)}
                      </li>
                    ))}
                    {formData.allowed_tools.length === 0 && (
                      <li className="text-gray-500">
                        No tools selected
                      </li>
                    )}
                  </ul>
                </div>
              </div>

              {error && <p className="text-red-600">{error}</p>}

              <div className="flex gap-4">
                <button
                  type="submit"
                  className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded"
                >
                  {editingAgent ? "Update Agent" : "Add Agent"}
                </button>
                <button
                  type="button"
                  onClick={handleCancel}
                  className="bg-gray-600 hover:bg-gray-700 text-white px-4 py-2 rounded"
                >
                  Cancel
                </button>
              </div>
            </form>
          </div>
        )}

        {/* Existing Agent Roles */}
        <div className="bg-white shadow rounded-lg p-6">
          <h2 className="text-xl font-semibold mb-4">
            Existing Agent Roles
          </h2>
          {loading ? (
            <p>Loading…</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-gray-200">
                <thead className="bg-gray-50">
                  <tr>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Agent Role
                    </th>
                    <th className="px-6 py-3	text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Description
                    </th>
                    <th className="px-6 py-3	text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Model
                    </th>
                    <th className="px-6 py-3	text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Reasoning
                    </th>
                    <th className="px-6 py-3	text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Tool Choice
                    </th>
                    <th className="px-6 py-3	text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Actions
                    </th>
                  </tr>
                </thead>
                <tbody className="bg-white divide-y divide-gray-200">
                  {agentTypes.length === 0 && (
                    <tr>
                      <td
                        colSpan="6"
                        className="px-6 py-4 whitespace-nowrap text-center text-gray-500"
                      >
                        No agent roles found.
                      </td>
                    </tr>
                  )}
                  {agentTypes.map((a) => {
                    const m = models.find((m) => m.id === a.model_id);
                    return (
                      <tr key={a.agent_role}>
                        <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                          {a.agent_role}
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                          {a.agent_description}
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                          {m
                            ? `${m.provider_display_name} / ${m.model_name}`
                            : "—"}
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                          {a.reasoning_level}
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                          {a.tool_choice}
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                          <button
                            onClick={() => openEditForm(a)}
                            className="mr-2 bg-green-500 hover:bg-green-600 text-white px-2 py-1 rounded"
                          >
                            Edit
                          </button>
                          <button
                            onClick={() => handleDelete(a.agent_role)}
                            className="bg-red-500 hover:bg-red-600 text-white px-2 py-1 rounded"
                          >
                            Delete
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
