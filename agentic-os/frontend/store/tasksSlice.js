import { createSlice } from "@reduxjs/toolkit";

const initialState = {
  // Each task has an id, a task name, and a user prompt.
  tasks: [
    // { id: "task1", taskName: "Task 1", userPrompt: "User prompt for task1" }
  ],
};

const tasksSlice = createSlice({
  name: "tasks",
  initialState,
  reducers: {
    addTask(state, action) {
      state.tasks.push(action.payload);
    },
    updateTask(state, action) {
      const { id, taskName, userPrompt } = action.payload;
      const task = state.tasks.find((t) => t.id === id);
      if (task) {
        task.taskName = taskName;
        task.userPrompt = userPrompt;
      }
    },
    deleteTask(state, action) {
      state.tasks = state.tasks.filter((t) => t.id !== action.payload);
    },
  },
});

export const { addTask, updateTask, deleteTask } = tasksSlice.actions;
export default tasksSlice.reducer;
