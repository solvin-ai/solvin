// pages/api/models.js

import modelManager from "../../lib/model_manager";

export default async function handler(req, res) {
  const { method, body, query } = req;

  if (method === "GET") {
    // ——— Fetch single model by model_id ———
    if (query.model_id) {
      try {
        const model = await modelManager.getModelById(query.model_id);
        if (!model) {
          return res.status(404).json({ error: "Model not found." });
        }
        return res.status(200).json({ model });
      } catch (error) {
        console.error("Error fetching model:", error);
        return res.status(500).json({ error: "Error fetching model." });
      }
    }

    // ——— List all models (?withProviders=1 for provider info) ———
    try {
      let models;
      if (query.withProviders) {
        models = await modelManager.listModelsWithProviderInfo();
      } else {
        models = await modelManager.listModels();
      }
      return res.status(200).json({ models });
    } catch (error) {
      console.error("Error fetching models:", error);
      return res.status(500).json({ error: "Error fetching models." });
    }
  } else if (method === "POST" || method === "PUT") {
    // Create or update a model
    const { id, provider_id, model_name, extra_info, supports_reasoning } = body || {};
    if (!provider_id || !model_name) {
      return res.status(400).json({ error: "provider_id and model_name are required." });
    }
    try {
      await modelManager.createOrUpdateModel({
        id,
        provider_id,
        model_name,
        extra_info,
        supports_reasoning,
      });
      return res.status(200).json({ message: "Model created/updated successfully." });
    } catch (error) {
      console.error("Error updating model:", error);
      return res.status(500).json({ error: "Error updating model." });
    }
  } else if (method === "DELETE") {
    // Delete a model by id
    const { id } = query;
    if (!id) {
      return res.status(400).json({ error: "Model id is required for deletion." });
    }
    try {
      await modelManager.deleteModel(id);
      return res.status(200).json({ message: "Model deleted successfully." });
    } catch (error) {
      console.error("Error deleting model:", error);
      return res.status(500).json({ error: "Error deleting model." });
    }
  } else {
    // Method not allowed
    res.setHeader("Allow", ["GET", "POST", "PUT", "DELETE"]);
    return res.status(405).end(`Method ${method} Not Allowed`);
  }
}
