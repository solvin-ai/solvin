// pages/api/v1/[...slug].js

import { SERVICE_URL_AGENTS, API_VERSION } from 'lib/constants'

export default async function handler(req, res) {
  const { slug } = req.query            // e.g. ['messages','list']
  const path = slug.join('/')           // "messages/list"
  const url = new URL(
    `${SERVICE_URL_AGENTS}/api/${API_VERSION}/${path}`,
    `${req.headers['x-forwarded-proto'] || 'http'}://${req.headers.host}`
  )

  // forward any incoming query parameters
  Object.entries(req.query)
    .filter(([k]) => k!=='slug')
    .forEach(([k,v]) => { if (v!=null) url.searchParams.set(k, v) })

  // build fetch options
  const opts = {
    method:  req.method,
    headers: { 'Content-Type': 'application/json' },
  }
  if (req.method !== 'GET' && req.body) {
    opts.body = JSON.stringify(req.body)
  }

  // proxy request
  const upstream = await fetch(url.toString(), opts)
  const contentType = upstream.headers.get('content-type') || ''
  res.status(upstream.status)
  upstream.headers.forEach((v,k) => {
    if (k==='content-length') return
    res.setHeader(k, v)
  })

  // stream or JSON
  if (contentType.includes('application/json')) {
    const json = await upstream.json()
    return res.json(json)
  } else {
    const buffer = await upstream.arrayBuffer()
    return res.send(Buffer.from(buffer))
  }
}
