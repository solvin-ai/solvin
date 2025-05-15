// lib/agent_manager.js

const path      = require("path");
const fs        = require("fs");
const sqlite3   = require("sqlite3");
const { open }  = require("sqlite");
const { DB_FILE } = require("./db");

async function openDB() {
  return open({
    filename: DB_FILE,
    driver:   sqlite3.Database,
  });
}

// Create/upgrade the DB schema if needed. Now supports model_id as FK.
async function initializeDB() {
  const db = await openDB();

  // Providers table
  await db.exec(`
    CREATE TABLE IF NOT EXISTS model_providers (
      id            INTEGER PRIMARY KEY AUTOINCREMENT,
      provider_name TEXT    UNIQUE NOT NULL,
      display_name  TEXT    NOT NULL,
      extra_info    TEXT    DEFAULT ''
    );
  `);

  // Models table
  await db.exec(`
    CREATE TABLE IF NOT EXISTS models (
      id           INTEGER PRIMARY KEY AUTOINCREMENT,
      provider_id  INTEGER NOT NULL,
      model_name   TEXT    NOT NULL,
      display_name TEXT    NOT NULL,
      extra_info   TEXT    DEFAULT '',
      UNIQUE (provider_id, model_name),
      FOREIGN KEY(provider_id) REFERENCES model_providers(id)
    );
  `);

  // Agent roles table
  await db.exec(`
    CREATE TABLE IF NOT EXISTS agent_roles (
      id                        INTEGER PRIMARY KEY AUTOINCREMENT,
      agent_role                TEXT    UNIQUE NOT NULL,
      agent_description         TEXT    DEFAULT '',
      allowed_tools             TEXT,
      default_developer_prompt  TEXT    DEFAULT '',
      default_user_prompt       TEXT    DEFAULT '',
      model_id                  INTEGER,
      reasoning_level           TEXT    DEFAULT 'medium',
      tool_choice               TEXT    DEFAULT 'auto',
      FOREIGN KEY(model_id) REFERENCES models(id)
    );
  `);

  await db.close();
}

// Upgrade: create missing tables/columns on an existing DB
async function checkAndUpgradeDBSchema() {
  if (!fs.existsSync(DB_FILE)) {
    // No DB at all yet → initialize everything
    await initializeDB();
    return;
  }

  const db = await openDB();

  // 1) If the agent_roles table is missing, create it wholesale
  const hasAgentRoles = await db.get(
    "SELECT name FROM sqlite_master WHERE type='table' AND name='agent_roles'"
  );
  if (!hasAgentRoles) {
    await db.exec(`
      CREATE TABLE IF NOT EXISTS agent_roles (
        id                        INTEGER PRIMARY KEY AUTOINCREMENT,
        agent_role                TEXT    UNIQUE NOT NULL,
        agent_description         TEXT    DEFAULT '',
        allowed_tools             TEXT,
        default_developer_prompt  TEXT    DEFAULT '',
        default_user_prompt       TEXT    DEFAULT '',
        model_id                  INTEGER,
        reasoning_level           TEXT    DEFAULT 'medium',
        tool_choice               TEXT    DEFAULT 'auto',
        FOREIGN KEY(model_id) REFERENCES models(id)
      );
    `);
  } else {
    // 2) Otherwise, add any missing columns to agent_roles
    const rows    = await db.all("PRAGMA table_info(agent_roles)");
    const columns = rows.map(col => col.name);

    const columnFixes = [
      { name: "agent_description",       sql: "ADD COLUMN agent_description TEXT DEFAULT ''" },
      { name: "allowed_tools",           sql: "ADD COLUMN allowed_tools TEXT" },
      { name: "default_developer_prompt", sql: "ADD COLUMN default_developer_prompt TEXT DEFAULT ''" },
      { name: "default_user_prompt",     sql: "ADD COLUMN default_user_prompt TEXT DEFAULT ''" },
      { name: "model_id",                sql: "ADD COLUMN model_id INTEGER" },
      { name: "reasoning_level",         sql: "ADD COLUMN reasoning_level TEXT DEFAULT 'medium'" },
      { name: "tool_choice",             sql: "ADD COLUMN tool_choice TEXT DEFAULT 'auto'" },
    ];

    for (const { name, sql } of columnFixes) {
      if (!columns.includes(name)) {
        await db.exec(`ALTER TABLE agent_roles ${sql}`);
      }
    }
  }

  // 3) Ensure the models table exists
  const hasModels = await db.get(
    "SELECT name FROM sqlite_master WHERE type='table' AND name='models'"
  );
  if (!hasModels) {
    await db.exec(`
      CREATE TABLE IF NOT EXISTS models (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        provider_id  INTEGER NOT NULL,
        model_name   TEXT    NOT NULL,
        display_name TEXT    NOT NULL,
        extra_info   TEXT    DEFAULT '',
        UNIQUE (provider_id, model_name),
        FOREIGN KEY(provider_id) REFERENCES model_providers(id)
      );
    `);
  }

  // 4) Ensure the model_providers table exists
  const hasProviders = await db.get(
    "SELECT name FROM sqlite_master WHERE type='table' AND name='model_providers'"
  );
  if (!hasProviders) {
    await db.exec(`
      CREATE TABLE IF NOT EXISTS model_providers (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        provider_name TEXT    UNIQUE NOT NULL,
        display_name  TEXT    NOT NULL,
        extra_info    TEXT    DEFAULT ''
      );
    `);
  }

  await db.close();
}

// Run schema check/migrations on load
checkAndUpgradeDBSchema();

/**
 * Always ensure "set_work_completed" is present in the tools array.
 */
function ensureDefaultTool(tools) {
  const arr = Array.isArray(tools) ? [...tools] : [];
  if (!arr.includes("set_work_completed")) {
    arr.push("set_work_completed");
  }
  return arr;
}

// Allowed tools for an agent (by agent_role)
async function getAllowedTools(agent_role) {
  const db  = await openDB();
  const row = await db.get(
    "SELECT allowed_tools FROM agent_roles WHERE agent_role = ?",
    agent_role
  );
  await db.close();

  if (row && row.allowed_tools) {
    try {
      return JSON.parse(row.allowed_tools);
    } catch (e) {
      console.error(`Error parsing allowed_tools for agent_role='${agent_role}':`, e);
    }
  }
  return [];
}

// Update allowed_tools for an agent by agent_role
async function setAllowedTools(agent_role, tools) {
  const finalTools      = ensureDefaultTool(tools);
  const allowedToolsJson = JSON.stringify(finalTools);
  const db              = await openDB();
  await db.run(
    "UPDATE agent_roles SET allowed_tools = ? WHERE agent_role = ?",
    allowedToolsJson,
    agent_role
  );
  await db.close();
}

// Update default prompts for an agent by agent_role
async function setDefaultPrompts(agent_role, developerPrompt, userPrompt) {
  const db = await openDB();
  await db.run(
    "UPDATE agent_roles SET default_developer_prompt = ?, default_user_prompt = ? WHERE agent_role = ?",
    developerPrompt || "",
    userPrompt      || "",
    agent_role
  );
  await db.close();
}

// Set or update agent details by agent_role
async function setAgentDetails({
  agent_role,
  agent_description,
  allowed_tools,
  default_developer_prompt,
  default_user_prompt,
  model_id,
  reasoning_level,
  tool_choice,
}) {
  if (!agent_role) throw new Error("agent_role is required");
  const db = await openDB();

  const existing = await db.get(
    "SELECT id FROM agent_roles WHERE agent_role = ?",
    agent_role
  );

  const finalTools = ensureDefaultTool(allowed_tools);
  const toolsJson  = JSON.stringify(finalTools);

  if (existing && existing.id) {
    // Update
    await db.run(
      `UPDATE agent_roles
         SET agent_description        = ?,
             allowed_tools            = ?,
             default_developer_prompt = ?,
             default_user_prompt      = ?,
             model_id                 = ?,
             reasoning_level          = ?,
             tool_choice              = ?
       WHERE agent_role = ?`,
      agent_description      || "",
      toolsJson,
      default_developer_prompt || "",
      default_user_prompt     || "",
      model_id !== undefined ? model_id : null,
      reasoning_level        || "medium",
      tool_choice            || "auto",
      agent_role
    );
  } else {
    // Insert
    await db.run(
      `INSERT INTO agent_roles
         (agent_role,
          agent_description,
          allowed_tools,
          default_developer_prompt,
          default_user_prompt,
          model_id,
          reasoning_level,
          tool_choice)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?)`,
      agent_role,
      agent_description        || "",
      toolsJson,
      default_developer_prompt || "",
      default_user_prompt      || "",
      model_id !== undefined ? model_id : null,
      reasoning_level          || "medium",
      tool_choice              || "auto"
    );
  }

  await db.close();
}

// Get the default prompts for a given agent_role
async function getDefaultPrompts(agent_role) {
  const db  = await openDB();
  const row = await db.get(
    "SELECT default_developer_prompt, default_user_prompt FROM agent_roles WHERE agent_role = ?",
    agent_role
  );
  await db.close();
  if (row) {
    return {
      developerPrompt: row.default_developer_prompt || "",
      userPrompt:      row.default_user_prompt      || ""
    };
  }
  return { developerPrompt: "", userPrompt: "" };
}

// Returns all agent role records (ordered by id)
async function listAgentTypes({ withModelInfo = false } = {}) {
  const db = await openDB();
  let rows;
  if (withModelInfo) {
    rows = await db.all(`
      SELECT
        agent_roles.*,
        models.model_name,
        models.display_name   AS model_display_name,
        model_providers.display_name AS provider_display_name,
        model_providers.provider_name AS provider_name
      FROM agent_roles
      LEFT JOIN models          ON agent_roles.model_id = models.id
      LEFT JOIN model_providers ON models.provider_id  = model_providers.id
      ORDER BY agent_roles.id
    `);
  } else {
    rows = await db.all("SELECT * FROM agent_roles ORDER BY id");
  }
  await db.close();
  return rows;
}

// Delete an agent record by agent_role
async function deleteAgentType(agent_role) {
  const db = await openDB();
  await db.run(
    "DELETE FROM agent_roles WHERE agent_role = ?",
    agent_role
  );
  await db.close();
}

// Retrieve an agent record by its unique agent_role.
async function getAgentByType(agent_role) {
  const db  = await openDB();
  const row = await db.get(
    "SELECT * FROM agent_roles WHERE agent_role = ?",
    agent_role
  );
  await db.close();
  return row;
}

module.exports = {
  getAllowedTools,
  setAllowedTools,
  setDefaultPrompts,
  setAgentDetails,
  getDefaultPrompts,
  listAgentTypes,
  deleteAgentType,
  getAgentByType,
};
