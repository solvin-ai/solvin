// pages/api/config/scopes.js

export default async function handler(req, res) {
  if (req.method !== "GET") {
    res.setHeader("Allow", ["GET"]);
    return res.status(405).json({ error: "Method not allowed" });
  }

  const apiUrl = process.env.SERVICE_URL_CONFIGS || "http://localhost:8010";
  try {
    const backendRes = await fetch(`${apiUrl}/config/scopes`);
    if (!backendRes.ok) {
      const errorText = await backendRes.text();
      throw new Error(errorText);
    }
    const scopes = await backendRes.json();
    return res.status(200).json(scopes);
  } catch (e) {
    return res.status(500).json({ error: "Failed to retrieve scopes", detail: String(e) });
  }
}
