const BASE = '/api'

// ── 청크 업로드 헬퍼 ──────────────────────────────────────────────────────────
import { uploadIfLarge, cleanupUpload } from './chunkUpload.js'

// ── 사용자별 API 키 (per-browser, localStorage) ───────────────────────────────
// 키는 이 브라우저에만 저장되고, 모든 LLM 호출(streamSSE)에 X-Anthropic-Api-Key
// 헤더로 자동 동봉된다 → 각자 자기 키로 자기 계정에 과금. 서버 전역 키 공유 없음.
const API_KEY_STORAGE = 'anthropic_api_key'

export function getStoredApiKey() {
  try { return localStorage.getItem(API_KEY_STORAGE) || '' } catch { return '' }
}
export function setStoredApiKey(key) {
  try {
    if (key) localStorage.setItem(API_KEY_STORAGE, key)
    else localStorage.removeItem(API_KEY_STORAGE)
  } catch { /* localStorage 비활성 환경 무시 */ }
}
export function clearStoredApiKey() {
  try { localStorage.removeItem(API_KEY_STORAGE) } catch { /* noop */ }
}
export function hasStoredApiKey() { return !!getStoredApiKey() }

/**
 * FormData에서 대용량 File을 청크 업로드로 교체한다.
 * fileFields: { formKey: File } 맵. 교체된 field는 formKey → formKey_ref 로 변경.
 * refs: 생성된 file_ref 목록 (파이프라인 완료 후 정리용)
 */
async function upgradeFormDataFiles(formData, fileFields) {
  const refs = []
  for (const [key, file] of Object.entries(fileFields)) {
    if (!file) continue
    const ref = await uploadIfLarge(file)
    if (ref) {
      formData.delete(key)
      formData.append(`${key}_ref`, ref)
      refs.push(ref)
    }
  }
  return refs
}

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

export async function setDbPath(dbPath) {
  const r = await fetch(`${BASE}/settings/db-path`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ db_path: dbPath }),
  })
  if (!r.ok) {
    const err = await r.json().catch(() => ({}))
    throw new Error(err.detail || 'DB 경로 설정 실패')
  }
  return r.json()
}

export async function getFacilityTypes() {
  const r = await fetch(`${BASE}/settings/facility-types`)
  return r.json()
}

export async function getMeta() {
  const r = await fetch(`${BASE}/settings/meta`)
  return r.json()
}

export async function getProjects(facilityType) {
  const url = facilityType
    ? `${BASE}/accumulate/projects?facility_type=${facilityType}`
    : `${BASE}/accumulate/projects`
  const r = await fetch(url)
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

export function getMyProjectDeepReportUrl(facilityType, competitionId, company) {
  return `${BASE}/accumulate/projects/${facilityType}/${competitionId}/submissions/${encodeURIComponent(company)}/deep-report`
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

export async function* addSubmission(facilityType, competitionId, formData) {
  const refs = await upgradeFormDataFiles(formData, {
    submission_pdf: formData.get('submission_pdf') instanceof File ? formData.get('submission_pdf') : null,
  })
  try {
    yield* streamSSE(`${BASE}/accumulate/projects/${facilityType}/${competitionId}/add-submission`, formData)
  } finally {
    refs.forEach(cleanupUpload)
  }
}

/**
 * Run accumulation pipeline. Returns an EventSource-like async iterator.
 * formData must include: competition_name, facility_type, year, client, location,
 *   brief_pdf (File), submissions_json (string), submission_pdfs (File[])
 */
export async function* runAccumulatePipeline(formData) {
  const { chunkUpload } = await import('./chunkUpload.js')
  const THRESHOLD = 25 * 1024 * 1024
  const refs = []

  // submission_pdfs: 하나라도 크면 전부 ref로 업로드 (backend는 섞음 불허)
  const subFiles = formData.getAll('submission_pdfs')
  const anyLarge = subFiles.some(f => f instanceof File && f.size > THRESHOLD)
  if (anyLarge) {
    const allRefs = []
    for (const file of subFiles) {
      const ref = await chunkUpload(file)
      allRefs.push(ref)
      refs.push(ref)
    }
    formData.delete('submission_pdfs')
    formData.set('submission_pdf_refs', JSON.stringify(allRefs))
  }

  // brief_pdf
  const briefFile = formData.get('brief_pdf')
  if (briefFile instanceof File && briefFile.size > THRESHOLD) {
    const ref = await chunkUpload(briefFile)
    formData.delete('brief_pdf')
    formData.set('brief_pdf_ref', ref)
    refs.push(ref)
  }

  try {
    yield* streamSSE(`${BASE}/accumulate/run`, formData)
  } finally {
    refs.forEach(cleanupUpload)
  }
}

/**
 * Run diagnosis pipeline. formData: facility_type, competition_name, brief_pdf, submission_pdf
 */
export async function* runDiagnosePipeline(formData) {
  const refs = await upgradeFormDataFiles(formData, {
    brief_pdf: formData.get('brief_pdf') instanceof File ? formData.get('brief_pdf') : null,
    submission_pdf: formData.get('submission_pdf') instanceof File ? formData.get('submission_pdf') : null,
  })
  try {
    yield* streamSSE(`${BASE}/diagnose/run`, formData)
  } finally {
    refs.forEach(cleanupUpload)
  }
}

/**
 * Run diagnosis against user-selected reference projects.
 * formData: facility_type, competition_name, reference_items_json, submission_pdf, brief_pdf (선택)
 */
export async function* runDiagnoseVsProjects(formData) {
  const refs = await upgradeFormDataFiles(formData, {
    brief_pdf: formData.get('brief_pdf') instanceof File ? formData.get('brief_pdf') : null,
    submission_pdf: formData.get('submission_pdf') instanceof File ? formData.get('submission_pdf') : null,
  })
  try {
    yield* streamSSE(`${BASE}/diagnose/run-vs-projects`, formData)
  } finally {
    refs.forEach(cleanupUpload)
  }
}

export function getDiagnosisReportUrl(filename) {
  return `${BASE}/diagnose/reports/${encodeURIComponent(filename)}`
}

// ── Archive search ──────────────────────────────────────────────────────────

export async function listArchive(facilityType = null) {
  const url = facilityType
    ? `${BASE}/archive/list?facility_type=${encodeURIComponent(facilityType)}`
    : `${BASE}/archive/list`
  const r = await fetch(url)
  if (!r.ok) throw new Error(`HTTP ${r.status}`)
  return r.json()
}

export async function searchArchive(query, facilityType = null, resultFilter = 'all') {
  const r = await fetch(`${BASE}/archive/search`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      query: query || '',
      facility_type: facilityType,
      result_filter: resultFilter,
    }),
  })
  if (!r.ok) {
    const err = await r.json().catch(() => ({}))
    throw new Error(err.detail || `검색 실패 (HTTP ${r.status})`)
  }
  return r.json()
}

export async function getArchiveDetail(facilityType, competitionId) {
  const r = await fetch(
    `${BASE}/archive/${encodeURIComponent(facilityType)}/${encodeURIComponent(competitionId)}`
  )
  if (!r.ok) {
    const err = await r.json().catch(() => ({}))
    throw new Error(err.detail || `상세 조회 실패 (HTTP ${r.status})`)
  }
  return r.json()
}

/**
 * Run single-submission pipeline (내 프로젝트 등록).
 * formData: competition_name, facility_type, year, client, location,
 *   company, result ("win"|"contracted"|"lose"), brief_pdf, submission_pdf
 */
export async function* runMyProjectPipeline(formData) {
  const refs = await upgradeFormDataFiles(formData, {
    brief_pdf: formData.get('brief_pdf') instanceof File ? formData.get('brief_pdf') : null,
    submission_pdf: formData.get('submission_pdf') instanceof File ? formData.get('submission_pdf') : null,
  })
  try {
    yield* streamSSE(`${BASE}/accumulate/run-single`, formData)
  } finally {
    refs.forEach(cleanupUpload)
  }
}

/**
 * Cross-compare selected submissions across projects.
 * items: [{facility_type, competition_id, company}]
 */
export async function getSubmission(facilityType, competitionId, company) {
  const r = await fetch(
    `${BASE}/accumulate/projects/${facilityType}/${competitionId}/submissions/${encodeURIComponent(company)}`
  )
  if (!r.ok) throw new Error(`HTTP ${r.status}`)
  return r.json()
}

export async function updateSubmission(facilityType, competitionId, company, body) {
  const r = await fetch(
    `${BASE}/accumulate/projects/${facilityType}/${competitionId}/submissions/${encodeURIComponent(company)}`,
    {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }
  )
  if (!r.ok) {
    const err = await r.json().catch(() => ({}))
    throw new Error(err.detail || `저장 실패 (HTTP ${r.status})`)
  }
  return r.json()
}

export function crossCompare(items) {
  const fd = new FormData()
  fd.append('items_json', JSON.stringify(items))
  return streamSSE(`${BASE}/accumulate/cross-compare`, fd)
}

// ── Brief analysis ───────────────────────────────────────────────────────────

export async function* runBriefAnalyze(formData) {
  const refs = await upgradeFormDataFiles(formData, {
    brief_pdf: formData.get('brief_pdf') instanceof File ? formData.get('brief_pdf') : null,
  })
  try {
    yield* streamSSE(`${BASE}/brief/analyze`, formData)
  } finally {
    refs.forEach(cleanupUpload)
  }
}

export function getBriefExportUrl(filename) {
  return `${BASE}/brief/exports/${encodeURIComponent(filename)}`
}

async function* streamSSE(url, formData) {
  const headers = {}
  const apiKey = getStoredApiKey()
  if (apiKey) headers['X-Anthropic-Api-Key'] = apiKey
  const response = await fetch(url, { method: 'POST', headers, body: formData ?? undefined })
  if (!response.ok) {
    // 401: API 키 미설정 — 사용자 친화적 메시지
    if (response.status === 401) {
      const err = await response.json().catch(() => ({}))
      throw new Error(err.detail || 'API 키가 설정되지 않았습니다. 설정 탭에서 Anthropic API 키를 입력해주세요.')
    }
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
