// pages/api/templates/export.js

import { exportTemplate } from '../../../lib/template_manager';

export default async function handler(req, res) {
  if (req.method !== 'POST') {
    res.setHeader('Allow', ['POST']);
    return res.status(405).end('Method Not Allowed');
  }

  const templateName = req.query.name || 'default';
  try {
    await exportTemplate(templateName);
    return res.status(200).json({ message: `Exported template "${templateName}"` });
  } catch (error) {
    console.error('Error exporting template:', error);
    return res.status(500).json({ error: 'Failed to export template' });
  }
}
