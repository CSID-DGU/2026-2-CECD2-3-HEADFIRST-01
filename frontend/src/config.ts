// 환경 변수를 한 곳에서 읽어서 앱 전체에서 사용
export const config = {
  /** 명시적으로 'false' 일 때만 실제 API 사용 */
  useMock: import.meta.env.VITE_USE_MOCK !== 'false',
  apiBaseUrl: import.meta.env.VITE_API_BASE_URL ?? '',
  maxUploadMB: Number(import.meta.env.VITE_MAX_UPLOAD_MB) || 25,
} as const

/** 업로드 허용 확장자 */
export const ACCEPTED_AUDIO_EXTENSIONS = ['.wav', '.mp3', '.m4a', '.flac', '.ogg', '.webm'] as const
