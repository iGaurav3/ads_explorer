import { useState } from 'react'
import { safeUrl } from '../api.js'

// User-supplied records (e.g. saved from LinkedIn's public Ad Library). Kept in the browser only,
// never sent to the server and never mixed with fetched results.

function parseCSV(text) {
  const rows = []
  let row = [], field = '', quoted = false
  for (let i = 0; i < text.length; i++) {
    const c = text[i]
    if (c === '"') {
      if (quoted && text[i + 1] === '"') { field += '"'; i++ } else quoted = !quoted
    } else if (c === ',' && !quoted) {
      row.push(field); field = ''
    } else if ((c === '\n' || c === '\r') && !quoted) {
      if (c === '\r' && text[i + 1] === '\n') i++
      row.push(field)
      if (row.some(x => x.trim())) rows.push(row)
      row = []; field = ''
    } else field += c
  }
  row.push(field)
  if (row.some(x => x.trim())) rows.push(row)
  const header = (rows.shift() || []).map(h => h.trim())
  return rows.map(r => Object.fromEntries(header.map((h, i) => [h, r[i] || ''])))
}

function normalize(raw) {
  const x = {}
  Object.keys(raw || {}).forEach(k => { x[k.toLowerCase().replace(/[\s.]+/g, '_')] = raw[k] })
  const pick = (...keys) => keys.map(k => x[k]).find(v => v !== undefined && v !== null && String(v).trim() !== '')
  return {
    platform: pick('platform', 'ad_platform') || 'Unspecified',
    headline: pick('headline', 'title') || '',
    body: pick('ad_copy', 'description', 'text', 'details') || '',
    url: safeUrl(pick('ad_url', 'url', 'source_url')),
    date: pick('published_date', 'first_seen', 'start_date') || 'Not disclosed',
    author: pick('author', 'advertiser_name', 'advertiser', 'company') || 'Not disclosed',
  }
}

export default function ImportPanel() {
  const [rows, setRows] = useState([])
  const [message, setMessage] = useState('')

  const onFile = async e => {
    const file = e.target.files[0]
    e.target.value = ''
    if (!file) return
    try {
      const text = await file.text()
      let value = file.name.toLowerCase().endsWith('.json') ? JSON.parse(text) : parseCSV(text)
      if (!Array.isArray(value)) value = value.ads || value.records || value.data || []
      const list = value.filter(v => v && typeof v === 'object').slice(0, 2000).map(normalize)
      setRows(list)
      setMessage(`Loaded ${list.length} row(s) from ${file.name}. The app cannot verify where imported data came from.`)
    } catch (err) {
      setMessage('Could not import file: ' + err.message)
    }
  }

  return (
    <section className="card imported">
      <div className="results-head">
        <h2>Imported records <span className="subtle">(user-supplied, unverified)</span></h2>
        <label className="button">
          Import CSV / JSON
          <input type="file" accept=".csv,.json,text/csv,application/json" hidden onChange={onFile} />
        </label>
      </div>
      <p className="subtle">For platforms without an open API (e.g. LinkedIn), save results from the public library and import them here.</p>
      {message && <p className="status-msg">{message}</p>}
      {rows.length > 0 && (
        <div className="table-wrap">
          <table>
            <thead><tr><th>S.No.</th><th>Ad Platform</th><th>Details</th><th>URL</th><th>Published Date</th><th>Author</th></tr></thead>
            <tbody>
              {rows.map((r, i) => (
                <tr key={i}>
                  <td className="num">{i + 1}</td>
                  <td>{r.platform}</td>
                  <td className="details"><strong>{r.headline || 'Not disclosed'}</strong><p className="clamp">{r.body}</p></td>
                  <td>{r.url ? <a href={r.url} target="_blank" rel="noopener noreferrer">Open ↗</a> : <span className="subtle">Not disclosed</span>}</td>
                  <td>{r.date}</td>
                  <td>{r.author}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}
