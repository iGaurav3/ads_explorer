import { useState } from 'react'
import { COUNTRIES, PLATFORMS } from '../api.js'

function badgeFor(cap) {
  if (!cap) return null
  if (cap.retrieval === 'link_only') return <span className="badge muted">Link only</span>
  if (cap.configured) return <span className="badge ok">Ready</span>
  return <span className="badge warn" title={cap.setup_hint || ''}>Needs setup</span>
}

export default function SearchForm({ capabilities, busy, onSubmit }) {
  const [form, setForm] = useState({
    company: '', domain: '', country: '', start_date: '', end_date: '', limit_per_platform: 100, meta_page_ids: '',
  })
  const [selected, setSelected] = useState(() => new Set(PLATFORMS.filter(p => p.default).map(p => p.id)))
  const [error, setError] = useState('')
  const set = key => e => setForm(f => ({ ...f, [key]: e.target.value }))

  const toggle = id => setSelected(prev => {
    const next = new Set(prev)
    next.has(id) ? next.delete(id) : next.add(id)
    return next
  })

  const submit = e => {
    e.preventDefault()
    if (!form.company.trim()) return setError('Company name is required.')
    if (!selected.size) return setError('Select at least one platform.')
    if (form.start_date && form.end_date && form.start_date > form.end_date) return setError('Start date must be before end date.')
    setError('')
    onSubmit({
      company: form.company.trim(),
      domain: form.domain.trim() || null,
      country: form.country || null,
      start_date: form.start_date || null,
      end_date: form.end_date || null,
      limit_per_platform: Math.min(500, Math.max(1, Number(form.limit_per_platform) || 100)),
      platforms: PLATFORMS.map(p => p.id).filter(id => selected.has(id)),
      meta_page_ids: form.meta_page_ids.split(/[\s,]+/).filter(Boolean),
    })
  }

  return (
    <form className="card search" onSubmit={submit}>
      <div className="grid-fields">
        <label className="field wide">
          <span>Company / brand name *</span>
          <input value={form.company} onChange={set('company')} placeholder="Nike, Salesforce, HubSpot…" maxLength={120} required />
        </label>
        <label className="field">
          <span>Website / domain</span>
          <input value={form.domain} onChange={set('domain')} placeholder="nike.com" maxLength={255} />
        </label>
        <label className="field">
          <span>Country</span>
          <select value={form.country} onChange={set('country')}>
            {COUNTRIES.map(([code, name]) => <option key={code} value={code}>{name}</option>)}
          </select>
        </label>
        <label className="field">
          <span>Start date</span>
          <input type="date" value={form.start_date} onChange={set('start_date')} />
        </label>
        <label className="field">
          <span>End date</span>
          <input type="date" value={form.end_date} onChange={set('end_date')} />
        </label>
        <label className="field">
          <span>Max records / platform</span>
          <input type="number" min="1" max="500" value={form.limit_per_platform} onChange={set('limit_per_platform')} />
        </label>
      </div>

      <fieldset className="platforms">
        <legend>
          Platforms
          <span className="legend-actions">
            <button type="button" className="link" onClick={() => setSelected(new Set(PLATFORMS.map(p => p.id)))}>Select all</button>
            <button type="button" className="link" onClick={() => setSelected(new Set())}>Deselect all</button>
          </span>
        </legend>
        <div className="platform-grid">
          {PLATFORMS.map(p => (
            <label key={p.id} className={'platform-option' + (selected.has(p.id) ? ' on' : '')}>
              <input type="checkbox" checked={selected.has(p.id)} onChange={() => toggle(p.id)} />
              <span className="platform-name">{p.label}</span>
              {badgeFor(capabilities[p.id])}
            </label>
          ))}
        </div>
      </fieldset>

      <details className="advanced">
        <summary>Advanced</summary>
        <label className="field">
          <span>Meta Page IDs (exact advertiser search, comma-separated)</span>
          <input value={form.meta_page_ids} onChange={set('meta_page_ids')} placeholder="e.g. 15087023444" />
        </label>
      </details>

      {error && <p className="form-error" role="alert">{error}</p>}
      <button className="primary" type="submit" disabled={busy}>{busy ? 'Fetching ads…' : 'Fetch Ads'}</button>
    </form>
  )
}
