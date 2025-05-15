// lib/model_manager.js

const sqlite3 = require("sqlite3");
const { open } = require("sqlite");
const { DB_FILE } = require("./db");

// Open (or create) the shared SQLite database
async function openDB() {
  return open({
    filename: DB_FILE,
    driver: sqlite3.Database,
  });
}

// Ensure model_providers and models tables exist (with display_name)
async function initializeModelAndProviderTables() {
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

  // Models table (with display_name + supports_reasoning)
  await db.exec(`
    CREATE TABLE IF NOT EXISTS models (
      id                 INTEGER PRIMARY KEY AUTOINCREMENT,
      provider_id        INTEGER NOT NULL,
      model_name         TEXT    NOT NULL,
      display_name       TEXT    NOT NULL DEFAULT '',
      extra_info         TEXT    DEFAULT '',
      supports_reasoning INTEGER NOT NULL DEFAULT 1,
      UNIQUE (provider_id, model_name),
      FOREIGN KEY(provider_id) REFERENCES model_providers(id)
    );
  `);

  await db.close();
}

// Auto‐initialize on load
initializeModelAndProviderTables().catch(console.error);

/**
 * List all models joined with their provider info.
 */
async function listModelsWithProviderInfo() {
  const db = await openDB();
  const rows = await db.all(`
    SELECT
      models.id,
      models.provider_id,
      models.model_name,
      models.display_name,
      models.extra_info,
      models.supports_reasoning,
      model_providers.provider_name       AS provider_name,
      model_providers.display_name        AS provider_display_name
    FROM models
    LEFT JOIN model_providers
      ON models.provider_id = model_providers.id
    ORDER BY provider_display_name, models.model_name
  `);
  await db.close();
  return rows;
}

/**
 * List raw models table.
 */
async function listModels() {
  const db = await openDB();
  const rows = await db.all("SELECT * FROM models ORDER BY id");
  await db.close();
  return rows;
}

/**
 * Create or update a model.
 * If `id` is passed, does an UPDATE; otherwise does an INSERT ... ON CONFLICT upsert.
 */
async function createOrUpdateModel({
  id,
  provider_id,
  model_name,
  display_name = model_name,
  extra_info = "",
  supports_reasoning = 1
}) {
  const db = await openDB();
  const sr = supports_reasoning ? 1 : 0;

  if (id) {
    // Update existing row by PK
    await db.run(
      `
      UPDATE models
      SET provider_id       = ?,
          model_name        = ?,
          display_name      = ?,
          extra_info        = ?,
          supports_reasoning = ?
      WHERE id = ?
      `,
      provider_id,
      model_name,
      display_name,
      extra_info,
      sr,
      id
    );
  } else {
    // Insert or upsert by (provider_id, model_name)
    await db.run(
      `
      INSERT INTO models
        (provider_id, model_name, display_name, extra_info, supports_reasoning)
      VALUES (?, ?, ?, ?, ?)
      ON CONFLICT(provider_id, model_name)
      DO UPDATE SET
        display_name       = excluded.display_name,
        extra_info         = excluded.extra_info,
        supports_reasoning = excluded.supports_reasoning
      `,
      provider_id,
      model_name,
      display_name,
      extra_info,
      sr
    );
  }

  await db.close();
}

/**
 * Get one model by its numeric ID with provider details.
 */
async function getModelById(id) {
  const db = await openDB();
  const row = await db.get(
    `
    SELECT
      models.*,
      model_providers.provider_name       AS provider_name,
      model_providers.display_name        AS provider_display_name
    FROM models
    LEFT JOIN model_providers
      ON models.provider_id = model_providers.id
    WHERE models.id = ?
    `,
    id
  );
  await db.close();
  return row;
}

/**
 * Get one model by (provider_id, model_name).
 */
async function getModelByProviderAndName(provider_id, model_name) {
  const db = await openDB();
  const row = await db.get(
    "SELECT * FROM models WHERE provider_id = ? AND model_name = ?",
    provider_id,
    model_name
  );
  await db.close();
  return row;
}

/**
 * Delete a model by its numeric ID.
 */
async function deleteModel(id) {
  const db = await openDB();
  await db.run("DELETE FROM models WHERE id = ?", id);
  await db.close();
}

module.exports = {
  listModels,
  listModelsWithProviderInfo,
  createOrUpdateModel,
  getModelById,
  getModelByProviderAndName,
  deleteModel,
};
