// lib/yaml_store.js

const fs   = require('fs');
const path = require('path');
const yaml = require('js-yaml');

const BASE = process.cwd();

/**
 * Ensure a directory exists, creating parents if needed.
 */
function ensureDir(dir) {
  if (!fs.existsSync(dir)) {
    fs.mkdirSync(dir, { recursive: true });
  }
}

/**
 * Load a YAML file (array of objects) from disk.
 * If the file does not exist, returns [].
 */
function loadYAML(relPath) {
  const file = path.join(BASE, relPath);
  if (!fs.existsSync(file)) return [];
  const content = fs.readFileSync(file, 'utf8');
  return yaml.load(content) || [];
}

/**
 * Serialize data to YAML and save to disk, creating parent folders.
 */
function saveYAML(relPath, data) {
  const file = path.join(BASE, relPath);
  ensureDir(path.dirname(file));
  const yamlStr = yaml.dump(data, { sortKeys: true });
  fs.writeFileSync(file, yamlStr, 'utf8');
}

module.exports = { loadYAML, saveYAML };
