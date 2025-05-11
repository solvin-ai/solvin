// pages/api/models.js

import modelManager from "../../lib/model_manager";

export default async function handler(req, res) {
  const { method, body, query } = req;

  if (method === "GET") {
    // List all models (?withProviders=1 for provider info)
    try {
      let models;
      if (query.withProviders) {
        models = await modelManager.listModelsWithProviderInfo();
      } else {
        models = await modelManager.listModels();
      }
      res.status(200).json({ models });
    } catch (error) {
      console.error("Error fetching models:", error);
      res.status(500).json({ error: "Error fetching models." });
    }
  } else if (method === "POST" || method === "PUT") {
    // Create or update a model
    const { id, provider_id, model_name, extra_info, supports_reasoning } = body || {};
    if (!provider_id || !model_name) {
      res.status(400).json({ error: "provider_id and model_name are required." });
      return;
    }
    try {
      await modelManager.createOrUpdateModel({
        id,
        provider_id,
        model_name,
        extra_info,
        supports_reasoning,
      });
      res.status(200).json({ message: "Model created/updated successfully." });
    } catch (error) {
      console.error("Error updating model:", error);
      res.status(500).json({ error: "Error updating model." });
    }
  } else if (method === "DELETE") {
    // Delete a model by id
    const { id } = query;
    if (!id) {
      res.status(400).json({ error: "Model id is required for deletion." });
      return;
    }
    try {
      await modelManager.deleteModel(id);
      res.status(200).json({ message: "Model deleted successfully." });
    } catch (error) {
      console.error("Error deleting model:", error);
      res.status(500).json({ error: "Error deleting model." });
    }
  } else {
    // Method not allowed
    res.setHeader("Allow", ["GET", "POST", "PUT", "DELETE"]);
    res.status(405).end(`Method ${method} Not Allowed`);
  }
}
