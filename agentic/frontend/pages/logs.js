// pages/logs.js

import { useState, useEffect } from "react";
import Header from "../components/Header";

export default function LogsPage() {
  const [logs, setLogs] = useState("");

  const fetchLogs = async () => {
    try {
      const res = await fetch("/api/logs");
      const data = await res.json();
      setLogs(data.logs);
    } catch (error) {
      console.error("Error fetching logs:", error);
      setLogs("Error fetching logs.");
    }
  };

  useEffect(() => {
    fetchLogs();
    const interval = setInterval(fetchLogs, 5000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="min-h-screen bg-gray-50">
      <Header
        title="Console Logs"
        breadcrumbs={[
          { href: "/", label: "Home" },
          { href: "/logs", label: "Logs" }
        ]}
      />
      <main className="max-w-7xl mx-auto py-10 px-4 sm:px-6 lg:px-8">
        <div className="bg-white shadow rounded-lg p-6">
          <pre className="bg-gray-100 p-4 shadow rounded overflow-auto h-[500px] whitespace-pre-wrap">
            {logs}
          </pre>
        </div>
      </main>
    </div>
  );
}
