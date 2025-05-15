// pages/api/tools.js

import path from "path";
import fs from "fs";

export default function handler(req, res) {
  // Directory containing your Python tool modules
  const toolsDir = path.join(
    process.cwd(),
    "..",
    "backend",
    "services",
    "tools",
    "src",
    "tools"
  );

  if (!fs.existsSync(toolsDir)) {
    return res.status(200).json({ tools: [] });
  }

  const files = fs.readdirSync(toolsDir);

  // Only return the canonical snake_case names, e.g. “agent_task”, “fetch_github_issues”, etc.
  const tools = files
    .filter(file => file.startsWith("tool_") && file.endsWith(".py"))
    .map(file => {
      // drop the "tool_" prefix and the ".py" extension
      return file.slice("tool_".length, -".py".length);
    });

  return res.status(200).json({ tools });
}
