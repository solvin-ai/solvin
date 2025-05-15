// pages/api/templates/list.js

import fs   from 'fs'
import path from 'path'

export default function handler(req, res) {
  if (req.method !== 'GET') {
    res.setHeader('Allow', ['GET'])
    return res.status(405).end('Method Not Allowed')
  }

  const baseDir = process.cwd()
  const tplDir  = path.join(baseDir, 'templates')

  if (!fs.existsSync(tplDir)) {
    return res.status(200).json([])
  }

  const entries = fs.readdirSync(tplDir, { withFileTypes: true })
  const names   = entries
    .filter((d) => d.isDirectory())
    .map((d) => d.name)

  return res.status(200).json(names)
}
