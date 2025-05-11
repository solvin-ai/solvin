import { createSlice } from "@reduxjs/toolkit";

const initialState = {
  // Each agent role now supports more fields.
  agentTypes: [
    // Example agent role:
    // {
    //   id: 1,
    //   agent_role: "root",
    //   agent_description: "",
    //   developerPrompt: "",
    //   userPrompt: "",
    //   allowedTools: ["tool_build", "tool_read_file"],
    //   model_id: null,
    //   reasoning_level: "medium",
    //   tool_choice: "auto"
    // }
  ],
};

const agentTypesSlice = createSlice({
  name: "agentTypes",
  initialState,
  reducers: {
    setAgentTypes(state, action) {
      // Replace entire agentTypes array (e.g. after refetch from backend)
      state.agentTypes = action.payload;
    },
    addAgentType(state, action) {
      state.agentTypes.push(action.payload);
    },
    updateAgentType(state, action) {
      const updated = action.payload;
      const index = state.agentTypes.findIndex((a) => a.id === updated.id);
      if (index !== -1) {
        state.agentTypes[index] = {
          ...state.agentTypes[index],
          ...updated,
        };
      }
    },
    deleteAgentType(state, action) {
      const id = action.payload;
      state.agentTypes = state.agentTypes.filter((a) => a.id !== id);
    },
  },
});

export const {
  setAgentTypes,
  addAgentType,
  updateAgentType,
  deleteAgentType,
} = agentTypesSlice.actions;

export default agentTypesSlice.reducer;
