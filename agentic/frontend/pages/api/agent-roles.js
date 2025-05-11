// pages/api/agent-roles.js

import agentManager from "../../lib/agent_manager";

//
// The only change here is that DEFAULT_TOOL is now snake_case.
// Everything returned by this API (and stored in the DB) will
// use raw snake_case tool names.
//
const DEFAULT_TOOL = "set_work_completed";

/**
 * Safely parse the JSON blob of tools (fallback to []).
 */
function parseTools(json) {
  try {
    const arr = JSON.parse(json);
    return Array.isArray(arr) ? arr : [];
  } catch {
    return [];
  }
}

/**
 * Ensure DEFAULT_TOOL is present in the array.
 */
function ensureDefaultTool(tools) {
  const arr = Array.isArray(tools) ? [...tools] : [];
  if (!arr.includes(DEFAULT_TOOL)) {
    arr.push(DEFAULT_TOOL);
  }
  return arr;
}

/**
 * If the client asks for a role that doesn't exist yet,
 * return a "blank" agent with our default tool.
 */
function makeBlankAgent(agent_role) {
  return {
    agent_role: agent_role || "",
    agent_description: "",
    allowed_tools: [DEFAULT_TOOL],
    default_developer_prompt: "",
    default_user_prompt: "",
    model_id: null,
    reasoning_level: "medium",
    tool_choice: "auto",
  };
}

export default async function handler(req, res) {
  const { method, query, body } = req;

  // ——— GET ———
  if (method === "GET") {
    // 1) Fetch single agent?
    if (query.agent_role) {
      try {
        const row = await agentManager.getAgentByType(query.agent_role);

        if (row) {
          // existing agent → parse tools & inject default
          const {
            id,
            default_user_prompt,
            allowed_tools: toolsJson,
            ...rest
          } = row;
          const tools = ensureDefaultTool(parseTools(toolsJson));
          return res.status(200).json({
            agent: { ...rest, allowed_tools: tools },
          });
        }

        // not found → return a blank agent so the UI can render a default-checked <li>
        return res
          .status(200)
          .json({ agent: makeBlankAgent(query.agent_role) });
      } catch (err) {
        console.error("GET /api/agent-roles?agent_role= error:", err);
        return res
          .status(500)
          .json({ error: "Error fetching agent role." });
      }
    }

    // 2) No agent_role → list all agent-types
    try {
      const rows = await agentManager.listAgentTypes();
      const agentTypes = rows.map(
        ({ id, default_user_prompt, allowed_tools: toolsJson, ...rest }) => {
          const tools = ensureDefaultTool(parseTools(toolsJson));
          return { ...rest, allowed_tools: tools };
        }
      );
      return res.status(200).json({ agentTypes });
    } catch (err) {
      console.error("GET /api/agent-roles error:", err);
      return res
        .status(500)
        .json({ error: "Error fetching agent roles." });
    }
  }

  // ——— POST — Create (or upsert) ———
  if (method === "POST") {
    const {
      agent_role,
      agent_description,
      allowed_tools,
      default_developer_prompt,
      default_user_prompt,
      model_id,
      reasoning_level,
      tool_choice,
    } = body || {};

    if (!agent_role) {
      return res
        .status(400)
        .json({ error: "agent_role is required." });
    }

    // inject default tool
    const finalTools = ensureDefaultTool(allowed_tools);

    try {
      await agentManager.setAgentDetails({
        agent_role,
        agent_description,
        allowed_tools: finalTools,
        default_developer_prompt,
        default_user_prompt,
        model_id,
        reasoning_level,
        tool_choice,
      });
      return res.status(200).json({
        message: "Agent role created/updated successfully.",
      });
    } catch (err) {
      console.error("POST /api/agent-roles error:", err);
      return res
        .status(500)
        .json({ error: "Error creating/updating agent role." });
    }
  }

  // ——— PUT — Update ———
  if (method === "PUT") {
    const {
      agent_role,
      agent_description,
      allowed_tools,
      default_developer_prompt,
      default_user_prompt,
      model_id,
      reasoning_level,
      tool_choice,
    } = body || {};

    if (!agent_role) {
      return res
        .status(400)
        .json({ error: "agent_role is required for update." });
    }

    // inject default tool
    const finalTools = ensureDefaultTool(allowed_tools);

    try {
      await agentManager.setAgentDetails({
        agent_role,
        agent_description,
        allowed_tools: finalTools,
        default_developer_prompt,
        default_user_prompt,
        model_id,
        reasoning_level,
        tool_choice,
      });
      return res
        .status(200)
        .json({ message: "Agent role updated successfully." });
    } catch (err) {
      console.error("PUT /api/agent-roles error:", err);
      return res
        .status(500)
        .json({ error: "Error updating agent role." });
    }
  }

  // ——— DELETE ———
  if (method === "DELETE") {
    const { agent_role } = query;
    if (!agent_role) {
      return res
        .status(400)
        .json({ error: "agent_role query parameter is required." });
    }
    try {
      await agentManager.deleteAgentType(agent_role);
      return res
        .status(200)
        .json({ message: "Agent role deleted successfully." });
    } catch (err) {
      console.error("DELETE /api/agent-roles error:", err);
      return res
        .status(500)
        .json({ error: "Error deleting agent role." });
    }
  }

  // ——— 405 ———
  res.setHeader("Allow", ["GET", "POST", "PUT", "DELETE"]);
  return res
    .status(405)
    .end(`Method ${method} Not Allowed`);
}
