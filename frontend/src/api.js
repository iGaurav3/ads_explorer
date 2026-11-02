export const PLATFORMS = [
  { id: 'linkedin', label: 'LinkedIn Ads', default: true },
  { id: 'meta', label: 'Meta Ads (Facebook & Instagram)', default: true },
  { id: 'google', label: 'Google Ads (Search, Display, YouTube)', default: true },
  { id: 'microsoft', label: 'Microsoft / Bing Ads', default: true },
  { id: 'tiktok', label: 'TikTok Ads' },
  { id: 'pinterest', label: 'Pinterest Ads' },
  { id: 'snapchat', label: 'Snapchat Ads' },
  { id: 'twitter', label: 'X / Twitter Ads' },
]

export const PLATFORM_NAMES = {
  linkedin: 'LinkedIn', meta: 'Meta', google: 'Google', microsoft: 'Microsoft',
  tiktok: 'TikTok', pinterest: 'Pinterest', snapchat: 'Snapchat', twitter: 'X / Twitter',
}

export const COUNTRIES = [
  ['', 'All countries'], ['AT', 'Austria'], ['BE', 'Belgium'], ['BG', 'Bulgaria'], ['HR', 'Croatia'], ['CY', 'Cyprus'],
  ['CZ', 'Czechia'], ['DK', 'Denmark'], ['EE', 'Estonia'], ['FI', 'Finland'], ['FR', 'France'], ['DE', 'Germany'],
  ['GR', 'Greece'], ['HU', 'Hungary'], ['IS', 'Iceland'], ['IE', 'Ireland'], ['IT', 'Italy'], ['LV', 'Latvia'],
  ['LI', 'Liechtenstein'], ['LT', 'Lithuania'], ['LU', 'Luxembourg'], ['MT', 'Malta'], ['NL', 'Netherlands'],
  ['NO', 'Norway'], ['PL', 'Poland'], ['PT', 'Portugal'], ['RO', 'Romania'], ['SK', 'Slovakia'], ['SI', 'Slovenia'],
  ['ES', 'Spain'], ['SE', 'Sweden'], ['TR', 'Turkey'], ['GB', 'United Kingdom'], ['US', 'United States'],
  ['CA', 'Canada'], ['AU', 'Australia'], ['IN', 'India'], ['BR', 'Brazil'],
]

export const STATUS_LABELS = {
  pending: 'Queued', running: 'Fetching…', success: 'Success', no_results: 'No matching ads',
  partial_results: 'Partial results', access_required: 'Setup / access required',
  unsupported_without_auth: 'Not available without login', rate_limited: 'Rate limited', blocked: 'Blocked', error: 'Error',
}

async function request(url, options) {
  const res = await fetch(url, options)
  const body = await res.json().catch(() => ({}))
  if (!res.ok) {
    const detail = Array.isArray(body.detail) ? body.detail.map(d => d.msg).join('; ') : body.detail
    throw new Error(detail || `HTTP ${res.status}`)
  }
  return body
}

export const api = {
  capabilities: () => request('/api/platforms/status'),
  status: fetchId => request('/api/platforms/status?' + new URLSearchParams({ fetch_id: fetchId })),
  fetchAds: payload => request('/api/ads/fetch', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
  }),
  listAds: params => request('/api/ads?' + toQuery(params)),
  getAd: id => request(`/api/ads/${encodeURIComponent(id)}`),
  exportUrl: (format, params) => '/api/ads/export?' + toQuery({ ...params, format }),
  capture: payload => request('/api/capture', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
  }),
  llmStatus: () => request('/api/llm/status'),
}

export function toQuery(params) {
  const q = new URLSearchParams()
  Object.entries(params).forEach(([k, v]) => {
    if (Array.isArray(v)) v.forEach(x => q.append(k, x))
    else if (v !== undefined && v !== null && v !== '') q.append(k, v)
  })
  return q.toString()
}

export function safeUrl(value) {
  try {
    const u = new URL(String(value || ''))
    return ['https:', 'http:'].includes(u.protocol) ? u.href : null
  } catch {
    return null
  }
}

export const RUN_KEY = 'ads-explorer-run'

export function saveRun(run) {
  try { localStorage.setItem(RUN_KEY, JSON.stringify(run)) } catch { /* storage unavailable */ }
}

export function loadRun() {
  try { return JSON.parse(localStorage.getItem(RUN_KEY) || 'null') } catch { return null }
}

// Runs on the ad-library page in the user's own browser: reads the visible text (links kept as
// [[LINK:url]] markers) and hands it to /capture.html via postMessage. It never fetches anything itself.
export function bookmarkletCode(origin) {
  const src = `(()=>{const B=new Set('DIV P LI TR TD TH SECTION ARTICLE H1 H2 H3 H4 H5 H6 BR TABLE UL OL HEADER FOOTER MAIN ASIDE NAV FIGURE BLOCKQUOTE DT DD'.split(' ')),S=new Set('SCRIPT STYLE NOSCRIPT TEMPLATE SVG IFRAME'.split(' ')),o=[];
const w=n=>{if(n.nodeType===3){o.push(n.nodeValue.replace(/\\s+/g,' '));return}if(n.nodeType!==1||S.has(n.tagName))return;
const c=getComputedStyle(n);if(c.display==='none'||c.visibility==='hidden')return;const b=B.has(n.tagName);if(b)o.push('\\n');
for(const k of n.childNodes)w(k);if(n.tagName==='A'&&n.href)o.push(' [[LINK:'+n.href+']] ');if(b)o.push('\\n')};
w(document.body);const d={type:'ads-capture',page_url:location.href,text:o.join('').replace(/[ \\t]+/g,' ').replace(/\\n\\s*/g,'\\n')};
const O=${JSON.stringify(origin)},t=window.open(O+'/capture.html','adscapture');if(!t){alert('Allow pop-ups for this site to send it to Ads Explorer.');return}
const h=e=>{if(e.source===t&&e.data==='ads-capture-ready'){t.postMessage(d,O);removeEventListener('message',h)}};addEventListener('message',h)})()`
  return 'javascript:' + encodeURIComponent(src.replace(/\n/g, ''))
}
