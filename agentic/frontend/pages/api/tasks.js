// pages/api/tasks.js

import { 
  checkDBSchema, 
  getTask, 
  getAllTasks, 
  createTask, 
  updateTask, 
  deleteTask 
} from '../../lib/tasks';

export default async function handler(req, res) {
  // Ensure the DB and its tasks table are set up before handling the request.
  await checkDBSchema();

  const { method } = req;
  try {
    if (method === 'GET') {
      const { task_name } = req.query;
      if (task_name) {
        // Fetch a single task by its name.
        const task = await getTask(task_name);
        if (task) {
          res.status(200).json({ task });
        } else {
          res.status(404).json({ error: "Task not found." });
        }
      } else {
        // Return all tasks.
        const tasks = await getAllTasks();
        res.status(200).json({ tasks });
      }
    } else if (method === 'POST') {
      // Create a new task.
      const { task_name, task_prompt } = req.body;
      if (!task_name) {
        res.status(400).json({ error: "task_name is required." });
        return;
      }
      await createTask(task_name, task_prompt || "");
      res.status(201).json({ message: "Task created successfully." });
    } else if (method === 'PUT') {
      // Update an existing task.
      const { id, task_name, task_prompt } = req.body;
      if (!id) {
        res.status(400).json({ error: "Task internal id is required for update." });
        return;
      }
      const result = await updateTask(id, task_name, task_prompt || "");
      if (result.changes === 0) {
        res.status(404).json({ error: "Task not found." });
      } else {
        res.status(200).json({ message: "Task updated successfully." });
      }
    } else if (method === 'DELETE') {
      // Delete a task.
      const { id } = req.query;
      if (!id) {
        res.status(400).json({ error: "Task id is required for deletion." });
        return;
      }
      const result = await deleteTask(id);
      if (result.changes === 0) {
        res.status(404).json({ error: "Task not found." });
      } else {
        res.status(200).json({ message: "Task deleted successfully." });
      }
    } else {
      res.setHeader("Allow", ["GET", "POST", "PUT", "DELETE"]);
      res.status(405).end(`Method ${method} is not allowed.`);
    }
  } catch (error) {
    console.error("Error in tasks API:", error);
    res.status(500).json({ error: "Internal server error." });
  }
}
