// lib/tasks.js

import { open } from 'sqlite'
import sqlite3 from 'sqlite3'
import fs from 'fs'
import { DB_FILE } from './db'   // your single controlplane.sqlite

/**
 * Open (or create) the shared SQLite database.
 */
export async function openDB() {
  return open({
    filename: DB_FILE,
    driver: sqlite3.Database,
  })
}

/**
 * Create the tasks table if it doesn't already exist.
 */
export async function initializeDB() {
  const db = await openDB()
  await db.exec(`
    CREATE TABLE IF NOT EXISTS tasks (
      id           INTEGER PRIMARY KEY AUTOINCREMENT,
      task_name    TEXT UNIQUE NOT NULL,
      task_prompt  TEXT DEFAULT ''
    );
  `)
  await db.close()
}

/**
 * Ensure the tasks table exists.
 * Does NOT delete or reinitialize the rest of the database.
 */
export async function checkDBSchema() {
  const db = await openDB()
  try {
    await db.exec(`
      CREATE TABLE IF NOT EXISTS tasks (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        task_name    TEXT UNIQUE NOT NULL,
        task_prompt  TEXT DEFAULT ''
      );
    `)
  } finally {
    await db.close()
  }
}

// Run this on module‐load so tasks are always in place before use:
checkDBSchema().catch(err => {
  console.error('Failed to ensure tasks table exists:', err)
})

/**
 * Retrieve a single task by name.
 */
export async function getTask(task_name) {
  const db = await openDB()
  const row = await db.get(
    `SELECT * FROM tasks WHERE task_name = ?`,
    task_name
  )
  await db.close()
  return row
}

/**
 * Retrieve all tasks.
 */
export async function getAllTasks() {
  const db = await openDB()
  const rows = await db.all(`SELECT * FROM tasks ORDER BY id`)
  await db.close()
  return rows
}

/**
 * Insert a new task.
 */
export async function createTask(task_name, task_prompt = "") {
  const db = await openDB()
  await db.run(
    `INSERT INTO tasks (task_name, task_prompt) VALUES (?, ?)`,
    task_name,
    task_prompt
  )
  await db.close()
}

/**
 * Update an existing task.
 */
export async function updateTask(id, task_name, task_prompt = "") {
  const db = await openDB()
  const result = await db.run(
    `UPDATE tasks SET task_name = ?, task_prompt = ? WHERE id = ?`,
    task_name,
    task_prompt,
    id
  )
  await db.close()
  return result
}

/**
 * Delete a task.
 */
export async function deleteTask(id) {
  const db = await openDB()
  const result = await db.run(
    `DELETE FROM tasks WHERE id = ?`,
    id
  )
  await db.close()
  return result
}
