// scripts/import-template.js

const { importTemplate } = require('../lib/template_manager');

const templateName = process.argv[2] || 'default';

importTemplate(templateName, { wipe: true })
  .then(() => {
    console.log(`✅ Imported template "${templateName}" successfully.`);
  })
  .catch(err => {
    console.error(`❌ Failed to import template "${templateName}":`, err);
    process.exit(1);
  });
