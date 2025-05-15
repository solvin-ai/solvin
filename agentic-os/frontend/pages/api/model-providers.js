// pages/api/model-providers.js

import modelProviderManager from "../../lib/model_provider_manager";

export default async function handler(req, res) {
  const { method, body, query } = req;

  if (method === "GET") {
    // List all providers
    try {
      const providers = await modelProviderManager.listProviders();
      res.status(200).json({ providers });
    } catch (error) {
      console.error("Error fetching providers:", error);
      res.status(500).json({ error: "Error fetching model providers." });
    }
  } else if (method === "POST" || method === "PUT") {
    // Create or update provider (by provider_name or id)
    const { id, provider_name, extra_info } = body || {};
    if (!provider_name) {
      res.status(400).json({ error: "provider_name is required." });
      return;
    }
    try {
      await modelProviderManager.createOrUpdateProvider({
        id,
        provider_name,
        extra_info,
      });
      res.status(200).json({ message: "Provider created/updated successfully." });
    } catch (error) {
      console.error("Error updating provider:", error);
      res.status(500).json({ error: "Error updating model provider." });
    }
  } else if (method === "DELETE") {
    const { id } = query;
    if (!id) {
      res.status(400).json({ error: "Provider id is required." });
      return;
    }
    try {
      await modelProviderManager.deleteProvider(id);
      res.status(200).json({ message: "Provider deleted successfully." });
    } catch (error) {
      console.error("Error deleting provider:", error);
      res.status(500).json({ error: "Error deleting model provider." });
    }
  } else {
    res.setHeader("Allow", ["GET", "POST", "PUT", "DELETE"]);
    res.status(405).end(`Method ${method} Not Allowed`);
  }
}
