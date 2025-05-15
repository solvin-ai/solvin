// store/store.js

import { configureStore } from "@reduxjs/toolkit";
import agentTypesReducer from "./agentTypesSlice";
import tasksReducer from "./tasksSlice";
import configReducer from "./configSlice";
import templatesReducer from "./templatesSlice";

const store = configureStore({
  reducer: {
    agentTypes: agentTypesReducer,
    tasks: tasksReducer,
    config: configReducer,
    templates: templatesReducer,
  },
});

export default store;
