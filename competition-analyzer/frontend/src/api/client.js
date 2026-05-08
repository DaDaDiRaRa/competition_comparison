const BASE = '/api'

export async function getSettings() {
  const r = await fetch(`${BASE}/settings`)
  return r.json()
}

export async function updateSettings(data) {
  const r = await fetch(`${BASE}/settings`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  return r.json()
}

export async function getApiKeyStatus() {
  const r = await fetch(`${BASE}/settings/api-key-status`)
  return r.json()
}

export async function setApiKey(apiKey) {
  const r = await fetch(`${BASE}/settings/api-key`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ api_key: apiKey }),
  })
  if (!r.ok) {
    const err = await r.json().catch(() => ({}))
    throw new Error(err.detail || 'API 키 설정 실패')
  }
  return r.json()
}

export async function clearApiKey() {
  const r = await fetch(`${BASE}/settings/api-key`, { method: 'DELETE' })
  return r.json()
}

export async function getFacilityTypes() {
  const r = await fetch(`${BASE}/settings/facility-types`)
  return r.json()
}

export async function getProjects(facilityType) {
  const url = facilityType
    ? `${BASE}/accumulate/projects?facility_type=${facilityType}`
    : `${BASE}/accumulate/projects`
  const r = await fetch(url)
  return r.json()
}

export async function getProject(facilityType, competitionId) {
  const r = await fetch(`${BASE}/accumulate/projects/${facilityType}/${competitionId}`)
  return r.json()
}

export async function getPatterns() {
  const r = await fetch(`${BASE}/patterns`)
  return r.json()
}

export async function getPattern(facilityType) {
  const r = await fetch(`${BASE}/patterns/${facilityType}`)
  return r.json()
}

export async function rebuildPattern(facilityType) {
  const r = await fetch(`${BASE}/patterns/rebuild/${facilityType}`, { method: 'POST' })
  return r.json()
}

export function getReportUrl(facilityType, competitionId) {
  return `${BASE}/accumulate/projects/${facilityType}/${competitionId}/report`
}

export function getSubmissionReportUrl(facilityType, competitionId, company) {
  return `${BASE}/accumulate/projects/${facilityType}/${competitionId}/submissions/${encodeURIComponent(company)}/report`
}

export function getCrossCompareReportUrl(filename) {
  return `${BASE}/accumulate/cross-compare/reports/${encodeURIComponent(filename)}`
}

export async function listCrossCompareReports() {
  const r = await fetch(`${BASE}/accumulate/cross-compare/reports`)
  return r.json()
}

export function rerunCompare(facilityType, competitionId) {
  return streamSSE(`${BASE}/accumulate/projects/${facilityType}/${competitionId}/rerun-compare`)
}

export async function rerenderReport(facilityType, competitionId) {
  const r = await fetch(
    `${BASE}/accumulate/projects/${facilityType}/${competitionId}/rerender-report`,
    { method: 'POST' },
  )
  if (!r.ok) {
    const err = await r.json().catch(() => ({}))
    throw new Error(err.detail || `리포트 재생성 실패 (HTTP ${r.status})`)
  }
  return r.json()
}

export function addSubmission(facilityType, competitionId, formData) {
  return streamSSE(`${BASE}/accumulate/projects/${facilityType}/${competitionId}/add-submission`, formData)
}

/**
 * Run accumulation pipeline. Returns an EventSource-like async iterator.
 * formData must include: competition_name, facility_type, year, client, location,
 *   brief_pdf (File), submissions_json (string), submission_pdfs (File[])
 */
export function runAccumulatePipeline(formData) {
  return streamSSE(`${BASE}/accumulate/run`, formData)
}

/**
 * Run diagnosis pipeline. formData: facility_type, competition_name, brief_pdf, submission_pdf
 */
export function runDiagnosePipeline(formData) {
  return streamSSE(`${BASE}/diagnose/run`, formData)
}

/**
 * Run diagnosis against user-selected reference projects.
 * formData: facility_type, competition_name, reference_items_json, submission_pdf, brief_pdf (선택)
 */
export function runDiagnoseVsProjects(formData) {
  return streamSSE(`${BASE}/diagnose/run-vs-projects`, formData)
}

/**
 * Run single-submission pipeline (내 프로젝트 등록).
 * formData: competition_name, facility_type, year, client, location,
 *   company, result ("win"|"contracted"|"lose"), brief_pdf, submission_pdf
 */
export function runMyProjectPipeline(formData) {
  return streamSSE(`${BASE}/accumulate/run-single`, formData)
}

/**
 * Cross-compare selected submissions across projects.
 * items: [{facility_type, competition_id, company}]
 */
export function crossCompare(items) {
  const fd = new FormData()
  fd.append('items_json', JSON.stringify(items))
  return streamSSE(`${BASE}/accumulate/cross-compare`, fd)
}

async function* streamSSE(url, formData) {
  const response = await fetch(url, { method: 'POST', body: formData ?? undefined })
  if (!response.ok) {
    const err = await response.text()
    throw new Error(`HTTP ${response.status}: ${err}`)
  }
  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buf = ''
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buf += decoder.decode(value, { stream: true })
    const lines = buf.split('\n')
    buf = lines.pop() ?? ''
    for (const line of lines) {
      if (line.startsWith('data: ')) {
        try {
          yield JSON.parse(line.slice(6))
        } catch {
          // skip malformed lines
        }
      }
    }
  }
}
