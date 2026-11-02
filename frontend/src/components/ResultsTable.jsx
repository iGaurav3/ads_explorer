import { useEffect, useMemo, useState } from 'react'
import { PLATFORM_NAMES, api, safeUrl } from '../api.js'

const COLUMNS = [
  { key: null, label: 'S.No.' },
  { key: 'platform', label: 'Ad Platform' },
  { key: null, label: 'Details' },
  { key: null, label: 'URL' },
  { key: 'published', label: 'Published Date' },
  { key: 'author', label: 'Author' },
]

function useDebounced(value, ms) {
  const [v, setV] = useState(value)
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms)
    return () => clearTimeout(t)
  }, [value, ms])
  return v
}

function CopyButton({ text }) {
  const [done, setDone] = useState(false)
  return (
    <button type="button" className="small" onClick={() => navigator.clipboard?.writeText(text).then(() => {
      setDone(true)
      setTimeout(() => setDone(false), 1200)
    })}>{done ? 'Copied' : 'Copy URL'}</button>
  )
}

export default function ResultsTable({ fetchId, platforms, refreshKey, onView }) {
  const [q, setQ] = useState('')
  const [platform, setPlatform] = useState([])
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [sort, setSort] = useState({ key: 'platform', order: 'asc' })
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(25)
  const [data, setData] = useState({ total: 0, ads: [] })
  const [error, setError] = useState('')
  const query = useDebounced(q, 300)

  const filters = useMemo(() => ({
    fetch_id: fetchId, platform, q: query, date_from: dateFrom, date_to: dateTo, sort: sort.key, order: sort.order,
  }), [fetchId, platform, query, dateFrom, dateTo, sort])

  useEffect(() => setPage(1), [filters, pageSize])
  useEffect(() => {
    if (!fetchId) return
    let live = true
    api.listAds({ ...filters, page, page_size: pageSize })
      .then(d => { if (live) { setData(d); setError('') } })
      .catch(e => live && setError(e.message))
    return () => { live = false }
  }, [filters, page, pageSize, fetchId, refreshKey])

  const pages = Math.max(1, Math.ceil(data.total / pageSize))
  const toggleSort = key => setSort(s => ({ key, order: s.key === key && s.order === 'asc' ? 'desc' : 'asc' }))

  return (
    <section className="card">
      <div className="results-head">
        <h2>Advertisements <span className="subtle">({data.total})</span></h2>
        <div className="exports">
          <a className="button" href={api.exportUrl('csv', filters)}>Export CSV</a>
          <a className="button" href={api.exportUrl('json', filters)}>Export JSON</a>
          <span className="subtle">Exports use the current filters.</span>
        </div>
      </div>

      <div className="toolbar">
        <input type="search" placeholder="Search headline, copy, advertiser, ID…" value={q} onChange={e => setQ(e.target.value)} />
        <select multiple value={platform} onChange={e => setPlatform([...e.target.selectedOptions].map(o => o.value))}
                aria-label="Filter by platform" title="Ctrl/Cmd-click to select several">
          {platforms.map(p => <option key={p} value={p}>{PLATFORM_NAMES[p]}</option>)}
        </select>
        <label>From <input type="date" value={dateFrom} onChange={e => setDateFrom(e.target.value)} /></label>
        <label>To <input type="date" value={dateTo} onChange={e => setDateTo(e.target.value)} /></label>
        {(q || platform.length || dateFrom || dateTo) ? (
          <button type="button" className="link" onClick={() => { setQ(''); setPlatform([]); setDateFrom(''); setDateTo('') }}>Clear filters</button>
        ) : null}
      </div>

      {error && <p className="form-error">{error}</p>}
      {!data.ads.length ? (
        <div className="empty">
          <strong>No advertisement records to show.</strong>
          <p>Only ads actually returned by a platform appear here. Check the platform status above for why a source returned nothing.</p>
        </div>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                {COLUMNS.map(c => (
                  <th key={c.label} className={c.key ? 'sortable' : ''} onClick={c.key ? () => toggleSort(c.key) : undefined}
                      aria-sort={sort.key === c.key ? (sort.order === 'asc' ? 'ascending' : 'descending') : undefined}>
                    {c.label}{sort.key === c.key ? (sort.order === 'asc' ? ' ▲' : ' ▼') : ''}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.ads.map((ad, i) => {
                const r = ad.row
                const url = safeUrl(r.url)
                const landing = safeUrl(r.landing_page_url)
                return (
                  <tr key={ad.id}>
                    <td className="num">{(page - 1) * pageSize + i + 1}</td>
                    <td>{r.platform}</td>
                    <td className="details">
                      <strong>{r.headline}</strong>
                      <p className="clamp">{r.body}</p>
                      <div className="meta-line">
                        <span>Type: {r.creative_type}</span>
                        <span>CTA: {r.call_to_action}</span>
                        <span>ID: {r.ad_id}</span>
                      </div>
                      {landing && <a href={landing} target="_blank" rel="noopener noreferrer nofollow">Landing page ↗</a>}
                      <button type="button" className="small" onClick={() => onView(ad.id)}>View Details</button>
                    </td>
                    <td>
                      {url ? (
                        <div className="url-cell">
                          <a href={url} target="_blank" rel="noopener noreferrer">Open ad ↗</a>
                          <CopyButton text={url} />
                        </div>
                      ) : <span className="subtle">Not disclosed</span>}
                    </td>
                    <td>{r.published_date}</td>
                    <td>{r.author}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}

      <div className="pager">
        <button type="button" disabled={page <= 1} onClick={() => setPage(p => p - 1)}>‹ Prev</button>
        <span>Page {page} of {pages}</span>
        <button type="button" disabled={page >= pages} onClick={() => setPage(p => p + 1)}>Next ›</button>
        <select value={pageSize} onChange={e => setPageSize(Number(e.target.value))} aria-label="Rows per page">
          {[10, 25, 50, 100].map(n => <option key={n} value={n}>{n} / page</option>)}
        </select>
      </div>
    </section>
  )
}
