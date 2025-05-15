import { createSlice } from "@reduxjs/toolkit";

const initialState = {
  config: {
    LLM_MODEL: "o3-mini",
    LLM_REASONING_LEVEL: "medium",
    API_URL_GITHUB: "",
    API_URL_CIRCLECI: "",
    API_URL_SONARQUBE: "",
    API_URL_JIRA: "",
    API_URL_SOURCEGRAPH: "",
    GITHUB_ORGANIZATION: "",
    GITHUB_FEATURE_BRANCH: "",
    GITHUB_PAGE_SIZE: 500,
    RUN_TOOLS_IN_CONTAINER: false,
    CASE_SENSITIVE_FILE_NAMES: true,
    LOG_LEVEL: "TRACE",
    ENABLE_TRACING: "true",
    TRACE_DETAIL_LEVEL: "off",
    TRACE_ALLOWED_PATH: "",
    INTERACTIVE_MODE: "timer",
    INTERACTIVE_TIMER_SECONDS: 0,
    MAX_ITERATIONS: 150,
    PRESERVATION_POLICY_MODE: "partial",
    CONTEXT_CHAR_LIMIT_KB: 150,
    FILE_SIZE_LIMIT_BYTES: 300000,
    PURGE_COOLDOWN_TURNS: 5
  },
};

const configSlice = createSlice({
  name: "config",
  initialState,
  reducers: {
    updateConfig(state, action) {
      state.config = { ...state.config, ...action.payload };
    },
    resetConfig(state) {
      state.config = initialState.config;
    },
  },
});

export const { updateConfig, resetConfig } = configSlice.actions;
export default configSlice.reducer;
