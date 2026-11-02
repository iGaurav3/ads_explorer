import { useCallback, useEffect, useRef, useState } from 'react'
import { api, loadRun, saveRun } from './api.js'
import SearchForm from './components/SearchForm.jsx'
import StatusPanel from './components/StatusPanel.jsx'
import ResultsTable from './components/ResultsTable.jsx'
import DetailsModal from './components/DetailsModal.jsx'
import ImportPanel from './components/ImportPanel.jsx'
import CapturePanel from './components/CapturePanel.jsx'

function newId() {
  return crypto.randomUUID ? crypto.randomUUID() : Date.now().toString(16) + Math.random().toString(16).slice(2, 10)
}

export default function App() {
  const [capabilities, setCapabilities] = useState({})
  const [run, setRun] = useState(loadRun) // { fetchId, platforms, company }; shared with /capture.html
  const [statuses, setStatuses] = useState({})
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [refreshKey, setRefreshKey] = useState(0)
  const [detailId, setDetailId] = useState(null)
  const poll = useRef(null)

  const refresh = useCallback(async fetchId => {
    try {
      const d = await api.status(fetchId)
      setStatuses(prev => {
        const next = { ...prev }
        d.platforms.forEach(p => { if (p.last) next[p.platform] = p.last })
        return next
      })
    } catch { /* next refresh will retry */ }
    setRefreshKey(k => k + 1)
  }, [])

  // A capture adds ads (and maybe a new platform) to the current search.
  const adoptCapture = useCallback(({ fetchId, platform }) => {
    setRun(prev => {
      const base = prev && prev.fetchId === fetchId ? prev : (loadRun()?.fetchId === fetchId ? loadRun() : { fetchId, company: null, platforms: [] })
      const next = base.platforms.includes(platform) ? base : { ...base, platforms: [...base.platforms, platform] }
      saveRun(next)
      return next
    })
    refresh(fetchId)
  }, [refresh])

  useEffect(() => {
    if (run) refresh(run.fetchId)
    let channel
    try {
      channel = new BroadcastChannel('ads-capture')
      channel.onmessage = e => e.data?.fetchId && adoptCapture(e.data)
    } catch { /* BroadcastChannel unsupported */ }
    return () => channel?.close()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    api.capabilities()
      .then(d => setCapabilities(Object.fromEntries(d.platforms.map(p => [p.platform, p]))))
      .catch(() => setError('Cannot reach the backend. Start it with `python server.py`.'))
    return () => clearInterval(poll.current)
  }, [])

  const onSubmit = async payload => {
    const fetchId = newId()
    const next = { fetchId, platforms: payload.platforms, company: payload.company }
    setRun(next)
    saveRun(next)
    setStatuses(Object.fromEntries(payload.platforms.map(p => [p, { status: 'pending' }])))
    setBusy(true)
    setError('')
    clearInterval(poll.current)
    poll.current = setInterval(async () => {
      try {
        const d = await api.status(fetchId)
        setStatuses(prev => {
          const next = { ...prev }
          d.platforms.forEach(p => { if (p.last) next[p.platform] = p.last })
          return next
        })
        setRefreshKey(k => k + 1)
      } catch { /* keep polling */ }
    }, 1000)
    try {
      const result = await api.fetchAds({ ...payload, fetch_id: fetchId })
      setStatuses(result.platforms)
    } catch (e) {
      setError('Fetch failed: ' + e.message)
    } finally {
      clearInterval(poll.current)
      setBusy(false)
      setRefreshKey(k => k + 1)
    }
  }

  const closeDetails = useCallback(() => setDetailId(null), [])

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand"><span className="logo">◉</span> OpenAds <span className="subtle">Explorer</span></div>
        <span className="subtle">Public ad-library data · no ad-account login</span>
      </header>

      <section className="hero">
        <h1>Fetch the ads a company is running.</h1>
        <p>Collects individual ad records from public ad libraries into one table, with no token: Microsoft is fetched
          automatically, and Meta, LinkedIn and Google are captured from pages you open in your own browser.</p>
      </section>

      {error && <p className="banner" role="alert">{error}</p>}
      <SearchForm capabilities={capabilities} busy={busy} onSubmit={onSubmit} />
      <CapturePanel run={run} statuses={statuses} onCaptured={r => adoptCapture({ fetchId: r.fetch_id, platform: r.platform })} />

      {run && (
        <>
          <StatusPanel platforms={run.platforms} statuses={statuses} />
          <ResultsTable fetchId={run.fetchId} platforms={run.platforms} refreshKey={refreshKey} onView={setDetailId} />
        </>
      )}
      <ImportPanel />
      {detailId && <DetailsModal id={detailId} onClose={closeDetails} />}
      <footer className="footer">No sample or demo ads are ever shown: every row comes from a platform response or a page you captured.</footer>
    </div>
  )
}
