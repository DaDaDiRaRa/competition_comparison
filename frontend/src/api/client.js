const BASE = '/api'

// ── 청크 업로드 헬퍼 ──────────────────────────────────────────────────────────
import { uploadIfLarge, cleanupUpload, chunkUpload } from './chunkUpload.js'

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

export async function deleteProject(facilityType, competitionId) {
  const r = await fetch(
    `${BASE}/accumulate/projects/${encodeURIComponent(facilityType)}/${encodeURIComponent(competitionId)}`,
    { method: 'DELETE' },
  )
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || '삭제 실패')
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

// 리포트/제안서 HTML을 파일로 저장. 서버에 ?download=1 을 붙이면 Content-Disposition:
// attachment 로 내려와 브라우저가 새 탭 대신 다운로드한다. 데스크톱(pywebview)은 저장
// 다이얼로그, 웹은 anchor[download] 로 처리.
export async function downloadReport(url, filename) {
  const dlUrl = url + (url.includes('?') ? '&' : '?') + 'download=1'
  if (window.pywebview?.api?.save_file) {
    const fullUrl = window.location.origin + dlUrl
    const res = await window.pywebview.api.save_file(fullUrl, filename)
    if (res && !res.ok && res.reason !== 'cancelled') {
      alert(`저장 실패: ${res.reason}`)
    }
    return
  }
  const a = document.createElement('a')
  a.href = dlUrl
  a.download = filename || ''
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
}

export async function listCrossCompareReports() {
  const r = await fetch(`${BASE}/accumulate/cross-compare/reports`)
  return r.json()
}

export async function rerenderCrossCompareReport(filename) {
  const r = await fetch(`${BASE}/accumulate/cross-compare/reports/${encodeURIComponent(filename)}/rerender`, { method: 'POST' })
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || '재렌더 실패')
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
  const refs = []
  const briefFiles = formData.getAll('brief_pdf')

  if (briefFiles.length > 1) {
    // 복수 파일: 모두 청크 업로드 → brief_pdf_refs JSON 배열
    const allRefs = []
    for (const file of briefFiles) {
      if (file instanceof File) {
        const ref = await chunkUpload(file)
        allRefs.push(ref)
        refs.push(ref)
      }
    }
    formData.delete('brief_pdf')
    formData.set('brief_pdf_refs', JSON.stringify(allRefs))
  } else {
    // 단일 파일: 소파일 직접 전송 / 대파일(25MB↑) 청크
    const single = briefFiles[0]
    if (single instanceof File) {
      const ref = await uploadIfLarge(single)
      if (ref) {
        formData.delete('brief_pdf')
        formData.set('brief_pdf_ref', ref)
        refs.push(ref)
      }
    }
  }

  try {
    yield* streamSSE(`${BASE}/brief/analyze`, formData)
  } finally {
    refs.forEach(cleanupUpload)
  }
}

export function getBriefExportUrl(filename) {
  return `${BASE}/brief/exports/${encodeURIComponent(filename)}`
}

export async function listBriefs() {
  const headers = {}
  const apiKey = getStoredApiKey()
  if (apiKey) headers['X-Anthropic-Api-Key'] = apiKey
  const r = await fetch(`${BASE}/brief/list`, { headers })
  if (!r.ok) throw new Error(await r.text())
  return r.json()
}

export async function deleteBrief(briefId) {
  const r = await fetch(`${BASE}/brief/${encodeURIComponent(briefId)}`, { method: 'DELETE' })
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || '삭제 실패')
  return r.json()
}

// AI 종합 해설만 재생성 (추출 재처리 없음, LLM 1콜). 사용자별 키 헤더 필요.
export async function reinterpretBrief(briefId) {
  const headers = {}
  const apiKey = getStoredApiKey()
  if (apiKey) headers['X-Anthropic-Api-Key'] = apiKey
  const r = await fetch(`${BASE}/brief/${encodeURIComponent(briefId)}/interpret`, { method: 'POST', headers })
  if (!r.ok) {
    const err = await r.json().catch(() => ({}))
    throw new Error(err.detail || `종합 해설 생성 실패 (HTTP ${r.status})`)
  }
  return r.json()
}

// VWorld 대지·맥락 분석 (geocoding + WMS + Claude vision). 사용자별 Anthropic 키 헤더 필요.
export async function analyzeSite(briefId, address, radiusM = 500) {
  const headers = { 'Content-Type': 'application/json' }
  const apiKey = getStoredApiKey()
  if (apiKey) headers['X-Anthropic-Api-Key'] = apiKey
  const r = await fetch(`${BASE}/brief/${encodeURIComponent(briefId)}/site-analyze`, {
    method: 'POST',
    headers,
    body: JSON.stringify({ address, radius_m: radiusM }),
  })
  if (!r.ok) {
    const err = await r.json().catch(() => ({}))
    throw new Error(err.detail || `대지 분석 실패 (HTTP ${r.status})`)
  }
  return r.json()
}

export function getBriefSiteImageUrl(briefId) {
  return `${BASE}/brief/${encodeURIComponent(briefId)}/site-image`
}

export async function getBriefSiteContext(briefId) {
  const r = await fetch(`${BASE}/brief/${encodeURIComponent(briefId)}/site-context`)
  if (!r.ok) throw new Error('대지 분석 결과 로드 실패')
  return r.json()
}

// 프로젝트 수주 제안서 생성 (수주 전략 처방, 추출 재처리 없음, LLM 1콜). 사용자별 키 헤더 필요.
export async function proposeBrief(briefId) {
  const headers = {}
  const apiKey = getStoredApiKey()
  if (apiKey) headers['X-Anthropic-Api-Key'] = apiKey
  const r = await fetch(`${BASE}/brief/${encodeURIComponent(briefId)}/propose`, { method: 'POST', headers })
  if (!r.ok) {
    const err = await r.json().catch(() => ({}))
    throw new Error(err.detail || `수주 제안서 생성 실패 (HTTP ${r.status})`)
  }
  return r.json()
}

// 경험 기반 처방 생성 (과거 축적 데이터 → 이 지침서 적용, 추출 재처리 없음, 최대 LLM 1콜).
// 과거 데이터 없으면 has_playbook:false + reason 반환 (LLM 미호출). 사용자별 키 헤더 필요.
export async function buildBriefPlaybook(briefId) {
  const headers = {}
  const apiKey = getStoredApiKey()
  if (apiKey) headers['X-Anthropic-Api-Key'] = apiKey
  const r = await fetch(`${BASE}/brief/${encodeURIComponent(briefId)}/playbook`, { method: 'POST', headers })
  if (!r.ok) {
    const err = await r.json().catch(() => ({}))
    throw new Error(err.detail || `경험 기반 처방 생성 실패 (HTTP ${r.status})`)
  }
  return r.json()
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
