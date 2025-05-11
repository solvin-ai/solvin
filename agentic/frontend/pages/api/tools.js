// pages/api/tools.js

import path from "path";
import fs from "fs";

export default function handler(req, res) {
  // New tools directory path: go up from process.cwd() and into backend/services/tools/src/tools
  const toolsDir = path.join(process.cwd(), "..", "backend", "services", "tools", "src", "tools");

  if (!fs.existsSync(toolsDir)) {
    return res.status(200).json({ tools: [] });
  }

  const files = fs.readdirSync(toolsDir);
  const tools = files
    .filter((file) => file.startsWith("tool_") && file.endsWith(".py"))
    .map((file) => {
      // Remove "tool_" prefix and ".py" extension
      let name = file.substring("tool_".length, file.lastIndexOf("."));
      // Convert underscores to spaces and capitalize each word
      name = name
        .split("_")
        .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
        .join(" ");
      return name;
    });

  res.status(200).json({ tools });
}
