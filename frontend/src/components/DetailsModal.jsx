import { useEffect, useState } from 'react'
import { api, safeUrl } from '../api.js'

const FIELDS = [
  ['platform', 'Platform'], ['ad_id', 'Ad ID'], ['advertiser_name', 'Advertiser'], ['author', 'Author / payer'],
  ['headline', 'Headline'], ['ad_copy', 'Ad copy'], ['description', 'Description'], ['creative_type', 'Creative type'],
  ['call_to_action', 'Call to action'], ['ad_url', 'Ad URL'], ['landing_page_url', 'Landing page'],
  ['published_date', 'Published date'], ['date_type', 'Date type'], ['first_seen', 'First seen'], ['last_seen', 'Last seen'],
  ['country', 'Country'], ['ad_status', 'Status'], ['source_type', 'Source'], ['retrieved_at', 'Retrieved at'],
]

function Value({ value }) {
  if (value === null || value === undefined || value === '') return <span className="subtle">Not disclosed</span>
  if (typeof value === 'object') return <pre>{JSON.stringify(value, null, 2)}</pre>
  const url = typeof value === 'string' && /^https?:\/\//.test(value) ? safeUrl(value) : null
  return url ? <a href={url} target="_blank" rel="noopener noreferrer nofollow">{url}</a> : <span>{String(value)}</span>
}

export default function DetailsModal({ id, onClose }) {
  const [ad, setAd] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    api.getAd(id).then(setAd).catch(e => setError(e.message))
    const onKey = e => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [id, onClose])

  const creative = ad && safeUrl(ad.creative_url)
  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" role="dialog" aria-modal="true" aria-label="Advertisement details" onClick={e => e.stopPropagation()}>
        <div className="modal-head">
          <h2>Advertisement details</h2>
          <button type="button" className="small" onClick={onClose}>Close</button>
        </div>
        {error && <p className="form-error">{error}</p>}
        {!ad && !error && <p>Loading…</p>}
        {ad && (
          <>
            {creative && <img className="creative" src={creative} alt="Ad creative provided by the source" referrerPolicy="no-referrer" loading="lazy" />}
            <dl className="kv">
              {FIELDS.map(([k, label]) => (
                <div key={k}><dt>{label}</dt><dd><Value value={ad[k]} /></dd></div>
              ))}
            </dl>
            {Object.keys(ad.source_metadata || {}).length > 0 && (
              <>
                <h3>Source-specific metadata</h3>
                <dl className="kv">
                  {Object.entries(ad.source_metadata).map(([k, v]) => (
                    <div key={k}><dt>{k}</dt><dd><Value value={v} /></dd></div>
                  ))}
                </dl>
              </>
            )}
          </>
        )}
      </div>
    </div>
  )
}
