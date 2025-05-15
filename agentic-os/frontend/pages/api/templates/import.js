// pages/api/templates/import.js

import { importTemplate } from 'lib/template_manager'

export default async function handler(req, res) {
  if (req.method !== 'POST') {
    res.setHeader('Allow', ['POST'])
    return res.status(405).end('Method Not Allowed')
  }

  // support both ?name=foo and ?name[]=foo
  const { name } = req.query
  const templateName = Array.isArray(name) ? name[0] : name || 'default'

  try {
    await importTemplate(templateName, { wipe: true })
    return res
      .status(200)
      .json({ message: `Imported template "${templateName}" successfully.` })
  } catch (error) {
    console.error('Error importing template:', error)
    return res
      .status(500)
      .json({ error: 'Failed to import template. Check server logs for details.' })
  }
}
