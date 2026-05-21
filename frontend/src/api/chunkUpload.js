/**
 * chunkUpload.js — 대용량 PDF 청크 업로드 유틸리티
 *
 * Cloud Run은 HTTP 요청 크기를 32MB로 제한한다.
 * 이 모듈은 파일을 CHUNK_SIZE 단위로 분할하여 순차 업로드한 뒤
 * 서버측 file_ref를 반환한다.
 */

const BASE = '/api'
const CHUNK_SIZE = 20 * 1024 * 1024  // 20MB — Cloud Run 32MB 한도 이내
const LARGE_FILE_THRESHOLD = 25 * 1024 * 1024  // 25MB 이상이면 청크 업로드

/**
 * 파일이 충분히 작으면 null 반환 (직접 업로드).
 * 크면 청크 업로드 후 file_ref 문자열 반환.
 *
 * @param {File} file
 * @param {function} [onProgress] (uploadedBytes, totalBytes) => void
 * @returns {Promise<string|null>} file_ref or null
 */
export async function uploadIfLarge(file, onProgress) {
  if (!file || file.size <= LARGE_FILE_THRESHOLD) return null
  return chunkUpload(file, onProgress)
}

/**
 * 파일을 청크로 분할 업로드. file_ref를 반환.
 */
export async function chunkUpload(file, onProgress) {
  // 1. 세션 시작
  const startRes = await fetch(`${BASE}/upload/start`, { method: 'POST' })
  if (!startRes.ok) throw new Error(`업로드 세션 시작 실패 (HTTP ${startRes.status})`)
  const { upload_id } = await startRes.json()

  const totalChunks = Math.ceil(file.size / CHUNK_SIZE)
  let uploaded = 0

  try {
    // 2. 청크 순차 업로드
    for (let i = 0; i < totalChunks; i++) {
      const start = i * CHUNK_SIZE
      const blob = file.slice(start, start + CHUNK_SIZE)

      const fd = new FormData()
      fd.append('chunk_index', String(i))
      fd.append('chunk', blob, file.name)

      const res = await fetch(`${BASE}/upload/chunk/${upload_id}`, {
        method: 'POST',
        body: fd,
      })
      if (!res.ok) {
        const err = await res.json().catch(() => ({}))
        throw new Error(err.detail || `청크 ${i + 1}/${totalChunks} 업로드 실패 (HTTP ${res.status})`)
      }

      uploaded += blob.size
      onProgress?.(uploaded, file.size)
    }

    // 3. 조립
    const fd = new FormData()
    fd.append('total_chunks', String(totalChunks))
    fd.append('filename', file.name)
    const finishRes = await fetch(`${BASE}/upload/finish/${upload_id}`, {
      method: 'POST',
      body: fd,
    })
    if (!finishRes.ok) {
      const err = await finishRes.json().catch(() => ({}))
      throw new Error(err.detail || `업로드 조립 실패 (HTTP ${finishRes.status})`)
    }
    const { file_ref } = await finishRes.json()
    return file_ref

  } catch (err) {
    // 실패 시 임시 파일 정리
    fetch(`${BASE}/upload/cleanup/${upload_id}`, { method: 'DELETE' }).catch(() => {})
    throw err
  }
}

/**
 * 파이프라인 완료 후 임시 파일 정리. upload_id는 file_ref의 첫 번째 세그먼트.
 */
export function cleanupUpload(file_ref) {
  if (!file_ref) return
  const upload_id = file_ref.split('/')[0]
  fetch(`${BASE}/upload/cleanup/${upload_id}`, { method: 'DELETE' }).catch(() => {})
}
