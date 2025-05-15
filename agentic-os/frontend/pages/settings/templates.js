// pages/settings/templates.js

import { useEffect, useState } from 'react'
import { useDispatch, useSelector } from 'react-redux'
import Header from '../../components/Header'
import {
  fetchTemplates,
  exportTemplate,
  importTemplate
} from '../../store/templatesSlice'

export default function TemplatesPage() {
  const dispatch    = useDispatch()
  const templates   = useSelector(s => s.templates.list)
  const status      = useSelector(s => s.templates.status)
  const error       = useSelector(s => s.templates.error)
  const lastAction  = useSelector(s => s.templates.lastAction)
  const [selected, setSelected] = useState('default')

  useEffect(() => {
    dispatch(fetchTemplates())
  }, [dispatch])

  const handleExport = () => {
    dispatch(exportTemplate(selected))
  }

  const handleImport = () => {
    if (
      confirm(
        `This will wipe current database data and import template "${selected}". Continue?`
      )
    ) {
      dispatch(importTemplate(selected))
    }
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <Header
        title="Templates"
        breadcrumbs={[
          { href: '/', label: 'Home' },
          { href: '/settings', label: 'Settings' },
          { href: '/settings/templates', label: 'Templates' }
        ]}
      />

      <main className="max-w-3xl mx-auto py-8 px-4">
        <h1 className="text-2xl font-semibold mb-6">Manage Templates</h1>

        {status === 'loading' && (
          <p className="mb-4 text-gray-600">Loading templates…</p>
        )}
        {status === 'failed' && (
          <p className="mb-4 text-red-600">Error: {error}</p>
        )}

        <div className="mb-4">
          <label htmlFor="template-select" className="block mb-2 font-medium">
            Choose template
          </label>
          <select
            id="template-select"
            className="w-full border border-gray-300 rounded p-2"
            value={selected}
            onChange={(e) => setSelected(e.target.value)}
          >
            {templates.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        </div>

        <div className="space-x-4">
          <button
            onClick={handleExport}
            disabled={status === 'exporting'}
            className="px-5 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50"
          >
            {status === 'exporting' ? 'Exporting…' : 'Export to files'}
          </button>

          <button
            onClick={handleImport}
            disabled={status === 'importing'}
            className="px-5 py-2 bg-green-600 text-white rounded hover:bg-green-700 disabled:opacity-50"
          >
            {status === 'importing' ? 'Importing…' : 'Import from files'}
          </button>
        </div>

        {status === 'idle' && lastAction && (
          <p className="mt-4 text-green-600">
            ✅{' '}
            {lastAction.type === 'export'
              ? `Exported "${selected}" successfully.`
              : `Imported "${selected}" successfully.`}
          </p>
        )}
      </main>
    </div>
  )
}
