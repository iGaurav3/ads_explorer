import { useEffect, useRef, useState } from 'react'
import { api, bookmarkletCode, PLATFORM_NAMES, safeUrl } from '../api.js'

const CAPTURE_PLATFORMS = ['meta', 'linkedin', 'google']

// No-token collection: the user opens the public library in their own browser and sends the page here.
export default function CapturePanel({ run, statuses, onCaptured }) {
  const link = useRef(null)
  const [llm, setLlm] = useState(null)
  const [pageUrl, setPageUrl] = useState('')
  const [content, setContent] = useState('')
  const [isHtml, setIsHtml] = useState(false)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')

  useEffect(() => {
    // React warns on javascript: hrefs, so the bookmarklet is set directly on the element.
    if (link.current) link.current.setAttribute('href', bookmarkletCode(window.location.origin))
    api.llmStatus().then(setLlm).catch(() => setLlm(null))
  }, [])

  const onFile = async e => {
    const file = e.target.files[0]
    e.target.value = ''
    if (!file) return
    setContent(await file.text())
    setIsHtml(true)
    setMessage(`Loaded ${file.name}. Paste the page's address above, then click Add ads.`)
  }

  const submit = async e => {
    e.preventDefault()
    setBusy(true)
    setMessage(llm?.available ? 'Reading ads… the local LLM can take a minute.' : 'Reading ads…')
    try {
      const result = await api.capture({
        page_url: pageUrl.trim(), [isHtml ? 'html' : 'text']: content,
        fetch_id: run?.fetchId, company: run?.company,
      })
      setMessage(result.captured ? `Added ${result.captured} ad(s) from ${PLATFORM_NAMES[result.platform]}.`
        : 'No ads recognized on that page.')
      setContent('')
      onCaptured(result)
    } catch (err) {
      setMessage('Capture failed: ' + err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="card">
      <h2>Capture from browser <span className="subtle">(no token needed)</span></h2>
      <p className="subtle">
        Meta, LinkedIn and Google block automated fetching, so you open the public library yourself and send the page here.
        The app reads the ads on it. Only text that is actually on the page is kept.
      </p>
      <ol className="steps">
        <li>
          Drag this to your bookmarks bar: <a ref={link} className="button" onClick={e => e.preventDefault()}
            title="Drag to the bookmarks bar">⇪ Send to Ads Explorer</a>
        </li>
        <li>
          Open the search:{' '}
          {CAPTURE_PLATFORMS.map(p => {
            const url = safeUrl(statuses[p]?.fallback_url)
            return url
              ? <a key={p} className="fallback" href={url} target="_blank" rel="noopener noreferrer">{PLATFORM_NAMES[p]} ↗</a>
              : <span key={p} className="subtle">{PLATFORM_NAMES[p]} </span>
          })}
          {!run && <span className="subtle"> (run a search above first to get links for your company)</span>}
        </li>
        <li>Scroll until the ads you want have loaded, then click the bookmark. Repeat for more pages.</li>
      </ol>
      <p className="status-msg subtle">
        Local LLM ({llm?.model || 'llama3'}): {llm?.available ? 'ready. It fills in fields the page rules miss.'
          : (llm?.detail || 'not reachable.') + ' Capture still works with the built-in rules.'}
      </p>

      <details className="advanced">
        <summary>Or paste the page / upload a saved page (Ctrl+S)</summary>
        <form onSubmit={submit} className="capture-form">
          <label className="field">Page address (URL)
            <input type="url" required value={pageUrl} onChange={e => setPageUrl(e.target.value)}
              placeholder="https://www.facebook.com/ads/library/?…" />
          </label>
          <label className="field">Page text (Ctrl+A, Ctrl+C on the page, then paste)
            <textarea rows={6} value={isHtml ? '' : content} placeholder={isHtml ? 'Saved HTML loaded' : ''}
              onChange={e => { setContent(e.target.value); setIsHtml(false) }} />
          </label>
          <div className="toolbar">
            <label className="button">Upload saved .html
              <input type="file" accept=".html,.htm,text/html" hidden onChange={onFile} />
            </label>
            <button className="primary" disabled={busy || !content || !pageUrl}>{busy ? 'Reading…' : 'Add ads'}</button>
          </div>
        </form>
      </details>
      {message && <p className="status-msg" role="status">{message}</p>}
    </section>
  )
}
