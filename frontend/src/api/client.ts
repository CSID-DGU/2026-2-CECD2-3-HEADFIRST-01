import { config } from '@/config'

export class ApiError extends Error {
  status?: number

  constructor(message: string, status?: number) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

/**
 * fetch 공통 래퍼
 * - baseURL 붙이기
 * - HTTP 에러 → ApiError 로 변환
 * - JSON 파싱
 */
export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response
  try {
    res = await fetch(`${config.apiBaseUrl}${path}`, init)
  } catch (err) {
    if (err instanceof DOMException && err.name === 'AbortError') throw err
    throw new ApiError('서버에 연결할 수 없습니다. 백엔드가 실행 중인지 확인해주세요.')
  }

  if (!res.ok) {
    let detail = ''
    try {
      const body = await res.json()
      const msg = body?.detail ?? body?.message
      if (typeof msg === 'string') detail = msg
    } catch {
      /* JSON 이 아닌 에러 응답은 무시 */
    }
    // 502~504: 개발 서버 프록시가 백엔드에 닿지 못한 경우가 대부분
    const fallback = [502, 503, 504].includes(res.status)
      ? `백엔드 서버에 연결할 수 없습니다. 서버가 실행 중인지 확인해주세요. (HTTP ${res.status})`
      : `요청이 실패했습니다. (HTTP ${res.status})`
    throw new ApiError(detail || fallback, res.status)
  }

  return res.json() as Promise<T>
}
