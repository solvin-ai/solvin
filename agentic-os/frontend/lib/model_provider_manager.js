// lib/model_provider_manager.js

const sqlite3 = require('sqlite3')
const { open } = require('sqlite')
const { DB_FILE } = require('./db')

/**
 * Open (or create) the shared SQLite database.
 */
async function openDB() {
  return open({
    filename: DB_FILE,
    driver:   sqlite3.Database,
  })
}

/**
 * Ensure the model_providers table exists.
 */
async function initializeProviderTable() {
  const db = await openDB()
  await db.exec(`
    CREATE TABLE IF NOT EXISTS model_providers (
      id            INTEGER PRIMARY KEY AUTOINCREMENT,
      provider_name TEXT    UNIQUE NOT NULL,
      display_name  TEXT    NOT NULL,
      extra_info    TEXT    DEFAULT ''
    );
  `)
  await db.close()
}

// Run on module load
initializeProviderTable().catch(err => {
  console.error('Failed to initialize model_providers table:', err)
})

/**
 * List all providers.
 */
async function listProviders() {
  const db   = await openDB()
  const rows = await db.all(
    'SELECT * FROM model_providers ORDER BY display_name, provider_name'
  )
  await db.close()
  return rows
}

/**
 * Create or update a provider.
 * If `id` is given, does an UPDATE; otherwise does an INSERT ... ON CONFLICT upsert.
 */
async function createOrUpdateProvider({ id, provider_name, display_name, extra_info }) {
  const db              = await openDB()
  const safeDisplayName = display_name && display_name.trim() !== ''
    ? display_name
    : provider_name

  if (id) {
    // Update existing row by primary key
    await db.run(
      `
      UPDATE model_providers
         SET provider_name = ?,
             display_name  = ?,
             extra_info    = ?
       WHERE id = ?
      `,
      provider_name,
      safeDisplayName,
      extra_info || '',
      id
    )
  } else {
    // Insert new or update by unique business key (provider_name)
    await db.run(
      `
      INSERT INTO model_providers (provider_name, display_name, extra_info)
      VALUES (?, ?, ?)
      ON CONFLICT(provider_name)
      DO UPDATE SET
        display_name = excluded.display_name,
        extra_info   = excluded.extra_info
      `,
      provider_name,
      safeDisplayName,
      extra_info || ''
    )
  }

  await db.close()
}

/**
 * Get a single provider by its numeric ID.
 */
async function getProviderById(id) {
  const db  = await openDB()
  const row = await db.get(
    'SELECT * FROM model_providers WHERE id = ?',
    id
  )
  await db.close()
  return row
}

/**
 * Delete a provider by its numeric ID.
 */
async function deleteProvider(id) {
  const db     = await openDB()
  await db.run(
    'DELETE FROM model_providers WHERE id = ?',
    id
  )
  await db.close()
}

module.exports = {
  listProviders,
  createOrUpdateProvider,
  getProviderById,
  deleteProvider,
}
