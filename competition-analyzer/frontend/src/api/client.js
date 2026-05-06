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

async function* streamSSE(url, formData) {
  const response = await fetch(url, { method: 'POST', body: formData })
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
