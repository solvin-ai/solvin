// pages/tasks.js

import { useState, useEffect } from "react";
import Header from "../../components/Header";

export default function TasksPage() {
  // List of tasks from the API
  const [tasks, setTasks] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  // Control whether the add/edit form is visible.
  // When editingTask is null we are adding a new task.
  const [showForm, setShowForm] = useState(false);
  const [editingTask, setEditingTask] = useState(null);

  // Extend form state to include an "id" field.
  const initialFormData = {
    id: null,
    task_name: "",
    task_prompt: ""
  };
  const [formData, setFormData] = useState(initialFormData);

  useEffect(() => {
    fetchTasks();
  }, []);

  const fetchTasks = async () => {
    setLoading(true);
    try {
      const res = await fetch("/api/tasks");
      const data = await res.json();
      setTasks(data.tasks || []);
    } catch (err) {
      setError("Failed to fetch tasks");
    }
    setLoading(false);
  };

  // Open form to add a new task.
  const openAddForm = () => {
    setEditingTask(null);
    setFormData(initialFormData);
    setError("");
    setShowForm(true);
  };

  // Open form to edit an existing task.
  const openEditForm = (task) => {
    setEditingTask(task);
    // Include the internal id when editing.
    setFormData({
      id: task.id,
      task_name: task.task_name,
      task_prompt: task.task_prompt || ""
    });
    setError("");
    setShowForm(true);
  };

  // Handle form submission (POST for add, PUT for edit).
  const handleFormSubmit = async (e) => {
    e.preventDefault();
    console.log("Submitting formData:", formData);
    const url = "/api/tasks";
    const method = editingTask ? "PUT" : "POST";
    try {
      const res = await fetch(url, {
        method,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(formData)
      });
      const result = await res.json();
      if (res.ok) {
        await fetchTasks();
        setShowForm(false);
      } else {
        console.error("API returned error:", result);
        setError(result.error || "Error saving task");
      }
    } catch (err) {
      console.error("Error saving task:", err);
      setError("Error saving task");
    }
  };

  // Delete a task using its internal id.
  const handleDelete = async (id) => {
    if (!confirm(`Are you sure you want to delete this task?`)) return;
    try {
      const res = await fetch(`/api/tasks?id=${id}`, { method: "DELETE" });
      if (res.ok) {
        await fetchTasks();
      } else {
        const data = await res.json();
        setError(data.error || "Error deleting task");
      }
    } catch (err) {
      setError("Error deleting task");
    }
  };

  const handleCancel = () => {
    setShowForm(false);
    setEditingTask(null);
    setFormData(initialFormData);
  };

  return (
    <div className="min-h-screen bg-gray-50">
      <Header
        title="Manage Tasks"
        breadcrumbs={[
          { href: "/", label: "Home" },
          { href: "/settings", label: "Settings" },
          { href: "/settings/tasks", label: "Tasks" }
        ]}
      />

      <main className="max-w-7xl mx-auto py-10 px-4 sm:px-6 lg:px-8">
        {/* The Add Task button is always visible */}
        <div className="mb-10">

          {!showForm && (
          <button
            type="button"
            onClick={openAddForm}
            className="bg-green-600 text-white px-5 py-2 rounded-md hover:bg-green-700 transition"
          >
            + Add Task
          </button>
          )}
        </div>

        {/* Form for adding/editing a task */}
        {showForm && (
          <div className="bg-white p-6 rounded-xl shadow-md mb-10">
            <h2 className="text-xl font-semibold mb-4">
              {editingTask ? "Edit Task" : "Add Task"}
            </h2>
            <form onSubmit={handleFormSubmit}>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                {/* Task Name */}
                <div>
                  <label className="block text-gray-700">Task Name</label>
                  <input
                    type="text"
                    name="task_name"
                    value={formData.task_name}
                    onChange={(e) =>
                      setFormData({ ...formData, task_name: e.target.value })
                    }
                    className="mt-1 block w-full border border-gray-300 rounded-md p-2"
                    placeholder="e.g. Translations"
                    required
                  />
                </div>
                {/* Task Prompt */}
                <div>
                  <label className="block text-gray-700">Task Prompt</label>
                  <textarea
                    name="task_prompt"
                    value={formData.task_prompt}
                    onChange={(e) =>
                      setFormData({ ...formData, task_prompt: e.target.value })
                    }
                    rows={16}
                    className="mt-1 block w-full border border-gray-300 rounded-md p-2"
                    placeholder="Enter task prompt..."
                  />
                </div>
              </div>
              {error && <p className="text-red-500 mt-4">{error}</p>}
              <div className="mt-6 space-x-4">
                <button
                  type="submit"
                  className="bg-blue-600 hover:bg-blue-700 text-white px-5 py-2 rounded-md transition"
                >
                  {editingTask ? "Update Task" : "Add Task"}
                </button>
                <button
                  type="button"
                  onClick={handleCancel}
                  className="bg-gray-600 hover:bg-gray-700 text-white px-5 py-2 rounded-md transition"
                >
                  Cancel
                </button>
              </div>
            </form>
          </div>
        )}

        {/* List of existing tasks (only showing Task Name and actions) */}
        <div className="bg-white p-6 rounded-xl shadow">
          <h2 className="text-xl font-semibold text-gray-800 mb-4">
            Existing Tasks
          </h2>
          {loading ? (
            <p>Loading...</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-gray-200">
                <thead>
                  <tr>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Task Name
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Actions
                    </th>
                  </tr>
                </thead>
                <tbody className="bg-white divide-y divide-gray-200">
                  {tasks.length > 0 ? (
                    tasks.map((task) => (
                      <tr key={task.id}>
                        <td className="px-6 py-4 whitespace-nowrap">
                          {task.task_name}
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap">
                          <div className="flex space-x-2">
                            <button
                              onClick={() => openEditForm(task)}
                              className="bg-green-500 text-white px-3 py-1 rounded hover:bg-green-600"
                            >
                              Edit
                            </button>
                            <button
                              onClick={() => handleDelete(task.id)}
                              className="bg-red-500 text-white px-3 py-1 rounded hover:bg-red-600"
                            >
                              Delete
                            </button>
                          </div>
                        </td>
                      </tr>
                    ))
                  ) : (
                    <tr>
                      <td colSpan="2" className="text-center py-4 text-gray-500">
                        No tasks found.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
