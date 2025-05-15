// pages/api/config/bulk_set.js

export default async function handler(req, res) {
  if (req.method !== "POST") {
    res.setHeader("Allow", ["POST"]);
    return res.status(405).json({ error: "Method not allowed" });
  }

  // Parse and check body
  const { items, scope = "global" } = req.body || {};
  if (!items || typeof items !== "object") {
    return res.status(400).json({ error: "Must provide 'items' as object" });
  }

  const apiUrl = process.env.SERVICE_URL_CONFIGS || "http://localhost:8010";
  try {
    // Proxy the bulk set call to FastAPI backend
    const backendRes = await fetch(`${apiUrl}/config/bulk_set`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ items, scope }),
    });

    if (!backendRes.ok) {
      const errorText = await backendRes.text();
      throw new Error(errorText);
    }

    return res.status(200).json({ ok: true });
  } catch (e) {
    return res.status(500).json({ error: "Failed to save config", detail: String(e) });
  }
}
