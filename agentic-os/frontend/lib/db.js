// lib/db.js

import fs   from 'fs';
import path from 'path';

const BASE_DIR = process.cwd();
const DB_DIR  = path.join(BASE_DIR, 'db');

// ensure the "db" folder exists
if (!fs.existsSync(DB_DIR)) {
  fs.mkdirSync(DB_DIR, { recursive: true });
}

// path to our single combined SQLite file
export const DB_FILE = path.join(DB_DIR, 'controlplane.sqlite');
