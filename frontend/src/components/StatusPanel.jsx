import { PLATFORM_NAMES, STATUS_LABELS, safeUrl } from '../api.js'

const TONE = {
  success: 'ok', no_results: 'muted', partial_results: 'warn', access_required: 'warn', unsupported_without_auth: 'muted',
  rate_limited: 'bad', blocked: 'bad', error: 'bad', running: 'live', pending: 'muted',
}

function time(value) {
  if (!value) return '—'
  const d = new Date(value)
  return isNaN(d) ? value : d.toLocaleTimeString()
}

export default function StatusPanel({ platforms, statuses }) {
  if (!platforms.length) return null
  return (
    <section className="card">
      <h2>Platform status</h2>
      <div className="status-list">
        {platforms.map(id => {
          const s = statuses[id] || { status: 'pending' }
          const fallback = safeUrl(s.fallback_url)
          return (
            <div key={id} className="status-row">
              <div className="status-main">
                <strong>{PLATFORM_NAMES[id]}</strong>
                <span className={'pill ' + (TONE[s.status] || 'muted')}>
                  {s.status === 'running' && <span className="spinner" aria-hidden="true" />}
                  {STATUS_LABELS[s.status] || s.status}
                </span>
                <span className="count">{s.record_count ?? 0} ads</span>
                <span className="time">{time(s.finished_at)}{s.cached ? ' · cached' : ''}</span>
              </div>
              {s.error && <p className="status-msg">{s.error}</p>}
              {s.setup_hint && <p className="status-msg hint">{s.setup_hint}</p>}
              {(s.warnings || []).map((w, i) => <p key={i} className="status-msg subtle">{w}</p>)}
              {s.coverage && <p className="status-msg subtle">Coverage: {s.coverage}</p>}
              {s.source_type === 'user_capture' && (
                <p className="status-msg subtle">Captured pages: {(s.captured_pages || []).length}</p>
              )}
              {fallback && ['partial_results', 'access_required', 'unsupported_without_auth', 'error', 'rate_limited', 'blocked', 'no_results'].includes(s.status) && (
                <a className="fallback" href={fallback} target="_blank" rel="noopener noreferrer">
                  Open public library ↗ <span className="subtle">(not a fetched record)</span>
                </a>
              )}
            </div>
          )
        })}
      </div>
    </section>
  )
}
