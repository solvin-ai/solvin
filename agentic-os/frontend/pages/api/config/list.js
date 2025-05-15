// pages/api/config/list.js

export default async function handler(req, res) {
  if (req.method !== "GET") {
    res.setHeader("Allow", ["GET"]);
    return res.status(405).json({ error: "Method not allowed" });
  }

  const scope = req.query.scope || "global";
  const apiUrl = process.env.SERVICE_URL_CONFIGS || "http://localhost:8010";
  try {
    // Fetch the raw entries from FastAPI
    const backendRes = await fetch(
      `${apiUrl}/config/list?scope=${encodeURIComponent(scope)}`
    );
    if (!backendRes.ok) {
      const text = await backendRes.text();
      throw new Error(text || backendRes.statusText);
    }
    const entries = await backendRes.json(); // [{ key, value }, ...]

    // Flatten to { key: parsedValue, … }
    const result = {};
    for (const { key, value } of entries) {
      let v = value;
      // If it's a string that looks like JSON array/object, try to parse it
      if (typeof v === "string") {
        const t = v.trim();
        if (
          (t.startsWith("[") && t.endsWith("]")) ||
          (t.startsWith("{") && t.endsWith("}"))
        ) {
          try {
            v = JSON.parse(t);
          } catch {
            // leave v as original string on parse error
          }
        }
      }
      result[key] = v;
    }

    return res.status(200).json(result);
  } catch (e) {
    return res
      .status(500)
      .json({ error: "Failed to retrieve config", detail: String(e) });
  }
}
