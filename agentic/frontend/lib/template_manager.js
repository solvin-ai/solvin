// lib/template_manager.js

import path from 'path'
import { loadYAML, saveYAML } from './yaml_store'
import {
  listProviders,
  createOrUpdateProvider,
  deleteProvider
} from './model_provider_manager'
import {
  listModelsWithProviderInfo,
  createOrUpdateModel,
  deleteModel
} from './model_manager'
import {
  listAgentTypes,
  setAgentDetails,
  deleteAgentType
} from './agent_manager'
import {
  getAllTasks,
  createTask,
  deleteTask
} from './tasks'

const TEMPLATES_DIR = 'templates'
function templatePath(templateName, fileName) {
  return path.join(TEMPLATES_DIR, templateName, fileName)
}

export async function exportTemplate(templateName = 'default') {
  // Providers
  const rawProviders = await listProviders()
  const providers = rawProviders.map(p => ({
    provider_name: p.provider_name,
    display_name:  p.display_name,
    extra_info:    p.extra_info
  }))
  saveYAML(templatePath(templateName, 'providers.yaml'), providers)
  console.log(`[export] Wrote ${providers.length} providers`)

  // Models
  const rawModels = await listModelsWithProviderInfo()
  const models = rawModels.map(m => ({
    provider_name:      m.provider_name,
    model_name:         m.model_name,
    display_name:       m.display_name,
    extra_info:         m.extra_info,
    supports_reasoning: Boolean(m.supports_reasoning)
  }))
  saveYAML(templatePath(templateName, 'models.yaml'), models)
  console.log(`[export] Wrote ${models.length} models`)

  // Agents
  const rawAgents = await listAgentTypes({ withModelInfo: true })
  const agents = rawAgents.map(a => ({
    agent_role:               a.agent_role,
    agent_description:        a.agent_description,
    allowed_tools:            a.allowed_tools ? JSON.parse(a.allowed_tools) : [],
    default_developer_prompt: a.default_developer_prompt,
    default_user_prompt:      a.default_user_prompt,
    reasoning_level:          a.reasoning_level,
    tool_choice:              a.tool_choice,
    provider_name:            a.provider_name,
    model_name:               a.model_name
  }))
  saveYAML(templatePath(templateName, 'agents.yaml'), agents)
  console.log(`[export] Wrote ${agents.length} agents`)

  // Tasks
  const rawTasks = await getAllTasks()
  const tasks    = rawTasks.map(t => ({
    task_name:   t.task_name,
    task_prompt: t.task_prompt
  }))
  saveYAML(templatePath(templateName, 'tasks.yaml'), tasks)
  console.log(`[export] Wrote ${tasks.length} tasks`)

  console.log(`✅ Exported template "${templateName}" to folder: ${TEMPLATES_DIR}/${templateName}/`)
}

export async function importTemplate(templateName = 'default', { wipe = true } = {}) {
  let count

  if (wipe) {
    // Providers
    const provs = await listProviders()
    count = provs.length
    for (const p of provs) await deleteProvider(p.id)
    if (count) console.log(`[import] Wiped ${count} providers`)

    // Models
    const mods = await listModelsWithProviderInfo()
    count = mods.length
    for (const m of mods) await deleteModel(m.id)
    if (count) console.log(`[import] Wiped ${count} models`)

    // Agents
    const ags = await listAgentTypes()
    count = ags.length
    for (const a of ags) await deleteAgentType(a.agent_role)
    if (count) console.log(`[import] Wiped ${count} agents`)

    // Tasks
    const ts = await getAllTasks()
    count = ts.length
    for (const t of ts) await deleteTask(t.id)
    if (count) console.log(`[import] Wiped ${count} tasks`)
  }

  // Providers
  const providersYaml = loadYAML(templatePath(templateName, 'providers.yaml'))
  for (const { provider_name, display_name, extra_info } of providersYaml) {
    await createOrUpdateProvider({ provider_name, display_name, extra_info })
    console.log(`[import][provider] Upserted "${provider_name}"`)
  }
  const provMap = new Map((await listProviders()).map(p => [p.provider_name, p.id]))
  console.log(`[import] Inserted/updated ${providersYaml.length} providers`)

  // Models
  const modelsYaml = loadYAML(templatePath(templateName, 'models.yaml'))
  for (const { provider_name, model_name, display_name, extra_info, supports_reasoning } of modelsYaml) {
    const provider_id = provMap.get(provider_name)
    if (provider_id == null) {
      throw new Error(`[import][model] Provider not found for "${provider_name}"`)
    }
    await createOrUpdateModel({
      provider_id,
      model_name,
      display_name,
      extra_info,
      supports_reasoning
    })
    console.log(`[import][model] Upserted "${provider_name}/${model_name}"`)
  }
  const modelMap = new Map(
    (await listModelsWithProviderInfo()).map(m => [`${m.provider_name}:${m.model_name}`, m.id])
  )
  console.log(`[import] Inserted/updated ${modelsYaml.length} models`)

  // Agents
  const agentsYaml = loadYAML(templatePath(templateName, 'agents.yaml'))
  for (const a of agentsYaml) {
    let model_id = null
    if (a.provider_name && a.model_name) {
      const key = `${a.provider_name}:${a.model_name}`
      model_id = modelMap.get(key)
      if (model_id == null) {
        console.warn(`[import][agent] ⚠️ Model not found for key="${key}", leaving model_id=null`)
      } else {
        console.log(`[import][agent] Linking agent "${a.agent_role}" → model "${key}"`)
      }
    } else {
      console.log(`[import][agent] No model specified for agent "${a.agent_role}", leaving model_id=null`)
    }
    await setAgentDetails({ ...a, model_id })
    console.log(`[import][agent] Upserted agent_role="${a.agent_role}"`)
  }
  console.log(`[import] Inserted/updated ${agentsYaml.length} agents`)

  // Tasks
  const tasksYaml = loadYAML(templatePath(templateName, 'tasks.yaml'))
  for (const { task_name, task_prompt } of tasksYaml) {
    await createTask(task_name, task_prompt)
    console.log(`[import][task] Upserted "${task_name}"`)
  }
  console.log(`[import] Inserted/updated ${tasksYaml.length} tasks`)

  console.log(`✅ Imported template "${templateName}" from folder: ${TEMPLATES_DIR}/${templateName}/`)
}
