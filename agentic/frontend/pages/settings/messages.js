// pages/settings/messages.js

import { useState, useEffect } from "react";
import Header from "../../components/Header";
import {
  AGENTS_PREFIX,
  MESSAGES_PREFIX,
} from "../../lib/constants";

export default function MessagesPage() {
  // Step 0: load all running agents (across repos) to get repo list
  const [repos, setRepos] = useState([]);
  const [repo, setRepo] = useState("");

  // Step 1: when repo selected → load agent roles
  const [roles, setRoles] = useState([]);
  const [role, setRole] = useState("");

  // Step 2: when role+repo selected → load running agents for that combo
  const [agents, setAgents] = useState([]);
  const [agentId, setAgentId] = useState("");

  // Step 3: when repo+role+agentId selected → load messages
  const [messages, setMessages] = useState([]);
  const [loading, setLoading]     = useState(false);
  const [error, setError]         = useState("");

  // controls for +Add form
  const [showForm, setShowForm] = useState(false);
  const [formData, setFormData] = useState({
    role: "", content: "", turn_id: ""
  });

  // --- Load all repos on mount ---
  useEffect(() => {
    fetch(`${AGENTS_PREFIX}/running/list`)
      .then((r) => r.json())
      .then((d) => {
        const arr = Array.isArray(d.data) ? d.data : [];
        const uniq = Array.from(new Set(arr.map((a) => a.repo_url))).filter(Boolean);
        setRepos(uniq);
      })
      .catch(console.error);
  }, []);

  // --- When repo changes, reset downstream and fetch registry of roles ---
  useEffect(() => {
    setRole("");    setRoles([]);
    setAgentId(""); setAgents([]);
    setMessages([]);
    if (!repo) return;

    fetch(`${AGENTS_PREFIX}/registry/list`)
      .then((r) => r.json())
      .then((d) => {
        const arr = Array.isArray(d.data) ? d.data : [];
        setRoles(arr.map((a) => a.agent_role));
      })
      .catch(console.error);
  }, [repo]);

  // --- When role changes, reset agentId/messages & fetch running agents for this repo+role ---
  useEffect(() => {
    setAgentId(""); setAgents([]); setMessages([]);
    if (!repo || !role) return;

    fetch(
      `${AGENTS_PREFIX}/running/list` +
      `?repo_url=${encodeURIComponent(repo)}` +
      `&agent_role=${encodeURIComponent(role)}`
    )
      .then((r) => r.json())
      .then((d) => setAgents(Array.isArray(d.data) ? d.data : []))
      .catch(console.error);
  }, [repo, role]);

  // --- When agentId changes, fetch messages ---
  useEffect(() => {
    setMessages([]);
    if (!repo || !role || !agentId) return;

    setLoading(true);
    fetch(
      `${MESSAGES_PREFIX}/list` +
      `?repo_url=${encodeURIComponent(repo)}` +
      `&agent_role=${encodeURIComponent(role)}` +
      `&agent_id=${encodeURIComponent(agentId)}`
    )
      .then((r) => {
        if (!r.ok) throw new Error("Failed to load messages");
        return r.json();
      })
      .then((arr) => setMessages(arr || []))
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [repo, role, agentId]);

  // --- Add message ---
  async function addMessage(e) {
    e.preventDefault();
    setError("");
    try {
      const payload = {
        repo_url:   repo,
        agent_role: role,
        agent_id:   agentId,
        role:       formData.role,
        content:    formData.content,
      };
      if (formData.turn_id) payload.turn_id = Number(formData.turn_id);

      const res = await fetch(`${MESSAGES_PREFIX}/add`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const j = await res.json();
      if (!res.ok) throw new Error(j.error || "Add failed");
      setShowForm(false);

      // refresh messages
      const refreshed = await fetch(
        `${MESSAGES_PREFIX}/list` +
        `?repo_url=${encodeURIComponent(repo)}` +
        `&agent_role=${encodeURIComponent(role)}` +
        `&agent_id=${encodeURIComponent(agentId)}`
      ).then((r) => r.json());
      setMessages(refreshed);
    } catch (e) {
      setError(e.message);
    }
  }

  // --- Delete message ---
  async function deleteMessage(id) {
    if (!confirm("Delete this message?")) return;
    setError("");
    try {
      const res = await fetch(
        `${MESSAGES_PREFIX}/remove` +
        `?repo_url=${encodeURIComponent(repo)}` +
        `&agent_role=${encodeURIComponent(role)}` +
        `&agent_id=${encodeURIComponent(agentId)}` +
        `&message_id=${id}`,
        { method: "DELETE" }
      );
      const j = await res.json();
      if (!res.ok) throw new Error(j.error || "Delete failed");
      setMessages((m) => m.filter((x) => x.message_id !== id));
    } catch (e) {
      setError(e.message);
    }
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <Header
        title="Manage Messages"
        breadcrumbs={[
          { href: "/", label: "Home" },
          { href: "/settings", label: "Settings" },
          { href: "/settings/messages", label: "Messages" },
        ]}
      />

      <main className="max-w-4xl mx-auto py-10 px-4 space-y-6">
        {/* Repo dropdown */}
        <div>
          <label className="block text-sm font-medium text-gray-700">Repository</label>
          <select
            value={repo}
            onChange={(e) => setRepo(e.target.value)}
            className="mt-1 w-full border-gray-300 rounded"
          >
            <option value="">— Select Repo —</option>
            {repos.map((r) => (
              <option key={r} value={r}>{r}</option>
            ))}
          </select>
        </div>

        {/* Role & Agent dropdowns */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium text-gray-700">Agent Role</label>
            <select
              value={role}
              onChange={(e) => setRole(e.target.value)}
              disabled={!roles.length}
              className="mt-1 w-full border-gray-300 rounded"
            >
              <option value="">— Select Role —</option>
              {roles.map((r) => (
                <option key={r} value={r}>{r}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700">Agent ID</label>
            <select
              value={agentId}
              onChange={(e) => setAgentId(e.target.value)}
              disabled={!agents.length}
              className="mt-1 w-full border-gray-300 rounded"
            >
              <option value="">— Select Agent —</option>
              {agents.map((a) => (
                <option key={a.agent_id} value={a.agent_id}>
                  {a.agent_id}{a.name ? ` (${a.name})` : ""}
                </option>
              ))}
            </select>
          </div>
        </div>

        {/* + Add Message */}
        {repo && role && agentId && !showForm && (
          <button
            onClick={() => { setFormData({ role: "", content: "", turn_id: "" }); setError(""); setShowForm(true); }}
            className="bg-green-600 text-white px-4 py-2 rounded"
          >
            + Add Message
          </button>
        )}
        {showForm && (
          <form onSubmit={addMessage} className="bg-white p-6 rounded shadow space-y-4">
            <div>
              <label className="block text-sm">Role</label>
              <input
                required
                value={formData.role}
                onChange={(e) => setFormData({ ...formData, role: e.target.value })}
                className="mt-1 w-full border-gray-300 rounded"
                placeholder="system/user/assistant"
              />
            </div>
            <div>
              <label className="block text-sm">Content</label>
              <textarea
                required
                value={formData.content}
                onChange={(e) => setFormData({ ...formData, content: e.target.value })}
                className="mt-1 w-full border-gray-300 rounded h-24"
              />
            </div>
            <div>
              <label className="block text-sm">Turn ID (optional)</label>
              <input
                type="number"
                value={formData.turn_id}
                onChange={(e) => setFormData({ ...formData, turn_id: e.target.value })}
                className="mt-1 w-32 border-gray-300 rounded"
              />
            </div>
            {error && <p className="text-red-600">{error}</p>}
            <div className="flex gap-4">
              <button type="submit" className="bg-blue-600 text-white px-4 py-2 rounded">
                Add
              </button>
              <button
                type="button"
                onClick={() => setShowForm(false)}
                className="bg-gray-600 text-white px-4 py-2 rounded"
              >
                Cancel
              </button>
            </div>
          </form>
        )}

        {/* Messages Table */}
        {repo && role && agentId && (
          <div className="bg-white p-6 rounded shadow">
            <h2 className="text-lg font-medium mb-4">Existing Messages</h2>
            {loading ? (
              <p>Loading…</p>
            ) : (
              <table className="w-full table-auto divide-y">
                <thead className="bg-gray-50">
                  <tr>
                    <th className="px-2 py-1 text-left text-xs">ID</th>
                    <th className="px-2 py-1 text-left text-xs">Role</th>
                    <th className="px-2 py-1 text-left text-xs">Turn</th>
                    <th className="px-2 py-1 text-left text-xs">Content</th>
                    <th className="px-2 py-1 text-left text-xs">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {messages.length === 0 && (
                    <tr>
                      <td colSpan="5" className="px-2 py-4 text-center text-gray-500">
                        No messages.
                      </td>
                    </tr>
                  )}
                  {messages.map((m) => (
                    <tr key={m.message_id}>
                      <td className="px-2 py-1 text-sm">{m.message_id}</td>
                      <td className="px-2 py-1 text-sm">{m.role}</td>
                      <td className="px-2 py-1 text-sm">{m.turn_id ?? "—"}</td>
                      <td className="px-2 py-1 text-sm">{m.content}</td>
                      <td className="px-2 py-1 text-sm">
                        <button
                          onClick={() => deleteMessage(m.message_id)}
                          className="bg-red-500 text-white px-2 py-1 rounded"
                        >
                          Delete
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
            {error && <p className="text-red-600 mt-2">{error}</p>}
          </div>
        )}
      </main>
    </div>
  );
}
