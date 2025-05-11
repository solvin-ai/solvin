import { promises as fs } from "fs";
import path from "path";

export default async function handler(req, res) {
  // Adjust the path to your log file location.
  const logFilePath = path.join(process.cwd(), "logs", "latest.log");
  try {
    const data = await fs.readFile(logFilePath, "utf8");
    res.status(200).json({ logs: data });
  } catch (error) {
    console.error("Error reading log file:", error);
    res.status(500).json({ logs: "Error reading logs." });
  }
}
