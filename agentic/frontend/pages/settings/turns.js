// pages/settings/turns.js

import { useState, useEffect } from "react";
import { useRouter } from "next/router";
import Header from "../../components/Header";

export default function TurnsPage() {
  const router = useRouter();
  const { agent_role, agent_id } = router.query;

  const [turns, setTurns] = useState([]);
  const [totalKb, setTotalKb] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [details, setDetails] = useState(null);

  useEffect(() => {
    if (agent_role && agent_id) fetchTurns();
  }, [agent_role, agent_id]);

  async function fetchTurns() {
    setLoading(true);
    setError("");
    try {
      const res = await fetch(
        `/api/turns/list?agent_role=${encodeURIComponent(agent_role)}&agent_id=${encodeURIComponent(agent_id)}`
      );
      if (!res.ok) throw new Error("Failed to load turns");
      const data = await res.json();
      setTurns(data.turns || []);
      setTotalKb(data.totalContextKb || 0);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  async function openDetails(turnNumber) {
    setLoading(true);
    setError("");
    try {
      const res = await fetch(
        `/api/turns/get?agent_role=${encodeURIComponent(agent_role)}&agent_id=${encodeURIComponent(agent_id)}&turn=${turnNumber}`
      );
      if (!res.ok) throw new Error("Failed to load turn details");
      const d = await res.json();
      setDetails(d);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  function closeDetails() {
    setDetails(null);
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <Header
        title="View Turns"
        breadcrumbs={[
          { href: "/", label: "Home" },
          { href: "/settings", label: "Settings" },
          { href: "/settings/turns", label: "Turns" },
        ]}
      />

      <main className="max-w-5xl mx-auto py-10 px-4">
        {!agent_role || !agent_id ? (
          <p className="text-red-600">
            Missing agent_role or agent_id in query parameters.
          </p>
        ) : (
          <>
            <div className="bg-white shadow rounded-lg p-6 mb-6">
              <h2 className="text-xl font-semibold mb-2">Turns List</h2>
              <p className="text-sm text-gray-600">
                Total context KB: {totalKb}
              </p>
            </div>

            <div className="bg-white shadow rounded-lg p-6 mb-6">
              {loading ? (
                <p>Loading…</p>
              ) : (
                <table className="min-w-full divide-y divide-gray-200">
                  <thead className="bg-gray-50">
                    <tr>
                      <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">
                        Turn #
                      </th>
                      <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">
                        Status
                      </th>
                      <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">
                        Tool
                      </th>
                      <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">
                        Actions
                      </th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-200">
                    {turns.length === 0 && (
                      <tr>
                        <td colSpan="4" className="px-4 py-4 text-center text-gray-500">
                          No turns found.
                        </td>
                      </tr>
                    )}
                    {turns.map((t) => (
                      <tr key={t.turn}>
                        <td className="px-4 py-2 text-sm">{t.turn}</td>
                        <td className="px-4 py-2 text-sm">{t.status}</td>
                        <td className="px-4 py-2 text-sm">
                          {t.toolName || "—"}
                        </td>
                        <td className="px-4 py-2 text-sm">
                          <button
                            onClick={() => openDetails(t.turn)}
                            className="bg-blue-600 hover:bg-blue-700 text-white px-2 py-1 rounded"
                          >
                            Details
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
              {error && <p className="text-red-600 mt-2">{error}</p>}
            </div>

            {/* Details Modal / Panel */}
            {details && (
              <div className="fixed inset-0 bg-black bg-opacity-30 flex items-center justify-center p-4">
                <div className="bg-white rounded-lg shadow-lg max-w-3xl w-full p-6 overflow-auto max-h-full">
                  <h3 className="text-lg font-semibold mb-4">
                    Turn Details: {details.turn}
                  </h3>
                  <pre className="bg-gray-100 p-4 rounded overflow-auto">
                    {JSON.stringify(details, null, 2)}
                  </pre>
                  <div className="mt-4 text-right">
                    <button
                      onClick={closeDetails}
                      className="bg-gray-600 hover:bg-gray-700 text-white px-4 py-2 rounded"
                    >
                      Close
                    </button>
                  </div>
                </div>
              </div>
            )}
          </>
        )}
      </main>
    </div>
  );
}
