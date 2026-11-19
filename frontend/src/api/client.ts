// frontend/src/api/client.ts
import { config } from '@/config'
import type { ApiResponse, ErrorCode } from '@/types/api'

/** 서버 errorCode + 프론트에서 붙이는 코드 */
export type ClientErrorCode =
  | ErrorCode
  | 'NETWORK' // 백엔드에 닿지 못함 (서버 꺼짐, 프록시 502~504)
  | 'BAD_RESPONSE' // 성공 응답이 공통 형식이 아님
  | 'UNKNOWN'

export class ApiError extends Error {
  status?: number
  code: ClientErrorCode

  constructor(message: string, status?: number, code: ClientErrorCode = 'UNKNOWN') {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
  }
}

const NETWORK_MESSAGE = '백엔드 서버에 연결할 수 없습니다. 서버가 실행 중인지 확인해주세요.'

async function send(path: string, init?: RequestInit): Promise<Response> {
  const headers = new Headers(init?.headers)
  headers.set('ngrok-skip-browser-warning', '1')

  try {
    return await fetch(`${config.apiBaseUrl}${path}`, { ...init, headers })
  } catch (err) {
    if (err instanceof DOMException && err.name === 'AbortError') throw err
    throw new ApiError(NETWORK_MESSAGE, undefined, 'NETWORK')
  }
}

/** JSON이 아니거나 비어 있으면 null */
async function readJson(res: Response): Promise<unknown> {
  try {
    return await res.json()
  } catch {
    return null
  }
}

function isEnvelope(body: unknown): body is ApiResponse<unknown> {
  return (
    typeof body === 'object' &&
    body !== null &&
    typeof (body as { success?: unknown }).success === 'boolean'
  )
}

function toError(res: Response, body: unknown): ApiError {
  // 1) 공통 형식 실패 응답: { success: false, message, data: { errorCode } }
  if (isEnvelope(body) && !body.success) {
    return new ApiError(body.message, res.status, body.data?.errorCode ?? 'UNKNOWN')
  }

  // 2) 공통 형식이 아닌 JSON 에러 (이전 규격 { detail } / { message })
  if (typeof body === 'object' && body !== null) {
    const { detail, message } = body as { detail?: unknown; message?: unknown }
    const msg = typeof detail === 'string' ? detail : typeof message === 'string' ? message : null
    if (msg) return new ApiError(msg, res.status)
  }

  // 3) JSON이 아닌 502~504: 개발 서버 프록시가 백엔드에 닿지 못한 경우
  if ([502, 503, 504].includes(res.status)) {
    return new ApiError(`${NETWORK_MESSAGE} (HTTP ${res.status})`, res.status, 'NETWORK')
  }

  return new ApiError(`요청이 실패했습니다. (HTTP ${res.status})`, res.status)
}

/**
 * 공통 응답 형식 API 호출
 * - 성공: data만 반환
 * - 실패: message + errorCode를 담은 ApiError
 */
export async function apiRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await send(path, init)
  const body = await readJson(res)

  if (!isEnvelope(body)) {
    if (!res.ok) throw toError(res, body)
    throw new ApiError('서버 응답 형식이 올바르지 않습니다.', res.status, 'BAD_RESPONSE')
  }
  if (!body.success) throw toError(res, body)
  return body.data as T
}

/**
 * 공통 형식이 아닌 응답용 (/health, 이전 규격)
 * - 성공: body 그대로 반환
 */
export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await send(path, init)
  const body = await readJson(res)
  if (!res.ok) throw toError(res, body)
  return body as T
}

/** JSON body POST용 init */
export function jsonBody(data: unknown, init?: RequestInit): RequestInit {
  return {
    ...init,
    method: init?.method ?? 'POST',
    headers: { 'Content-Type': 'application/json', ...init?.headers },
    body: JSON.stringify(data),
  }
}