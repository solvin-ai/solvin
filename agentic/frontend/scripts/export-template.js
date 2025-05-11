// scripts/export-template.js

const { exportTemplate } = require('../lib/template_manager');

const templateName = process.argv[2] || 'default';

exportTemplate(templateName)
  .then(() => {
    console.log(`✅ Exported template "${templateName}" successfully.`);
  })
  .catch(err => {
    console.error(`❌ Failed to export template "${templateName}":`, err);
    process.exit(1);
  });
