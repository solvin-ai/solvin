// store/templatesSlice.js

import { createSlice, createAsyncThunk } from '@reduxjs/toolkit'

// Thunk to fetch the list of available templates
export const fetchTemplates = createAsyncThunk(
  'templates/fetchTemplates',
  async () => {
    const res = await fetch('/api/templates/list')
    if (!res.ok) throw new Error('Failed to load templates')
    return res.json()   // expected to be an array of template names
  }
)

// Thunk to export the current DB state into YAML under a named template
export const exportTemplate = createAsyncThunk(
  'templates/exportTemplate',
  async (templateName) => {
    const res = await fetch(`/api/templates/export?name=${templateName}`, {
      method: 'POST'
    })
    if (!res.ok) throw new Error('Export failed')
    return res.json()
  }
)

// Thunk to import a named YAML template into the DB (wiping first)
export const importTemplate = createAsyncThunk(
  'templates/importTemplate',
  async (templateName) => {
    const res = await fetch(`/api/templates/import?name=${templateName}`, {
      method: 'POST'
    })
    if (!res.ok) throw new Error('Import failed')
    return res.json()
  }
)

const templatesSlice = createSlice({
  name: 'templates',
  initialState: {
    list: [],         // array of template names, e.g. ['default','staging']
    status: 'idle',   // 'idle' | 'loading' | 'exporting' | 'importing' | 'failed'
    error: null,
    lastAction: null  // { type: 'import'|'export', response: {...} }
  },
  reducers: {},
  extraReducers: builder => {
    builder
      // fetchTemplates
      .addCase(fetchTemplates.pending, (state) => {
        state.status = 'loading'
        state.error = null
      })
      .addCase(fetchTemplates.fulfilled, (state, action) => {
        state.status = 'idle'
        state.list = action.payload
      })
      .addCase(fetchTemplates.rejected, (state, action) => {
        state.status = 'failed'
        state.error = action.error.message
      })

      // exportTemplate
      .addCase(exportTemplate.pending, (state) => {
        state.status = 'exporting'
        state.error = null
      })
      .addCase(exportTemplate.fulfilled, (state, action) => {
        state.status = 'idle'
        state.lastAction = { type: 'export', response: action.payload }
      })
      .addCase(exportTemplate.rejected, (state, action) => {
        state.status = 'failed'
        state.error = action.error.message
      })

      // importTemplate
      .addCase(importTemplate.pending, (state) => {
        state.status = 'importing'
        state.error = null
      })
      .addCase(importTemplate.fulfilled, (state, action) => {
        state.status = 'idle'
        state.lastAction = { type: 'import', response: action.payload }
      })
      .addCase(importTemplate.rejected, (state, action) => {
        state.status = 'failed'
        state.error = action.error.message
      })
  }
})

export default templatesSlice.reducer
