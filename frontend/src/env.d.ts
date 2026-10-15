/// <reference types="vite/client" />

// .env 에서 읽어오는 값들의 타입 정의
interface ImportMetaEnv {
  readonly VITE_USE_MOCK?: string
  readonly VITE_API_BASE_URL?: string
  readonly VITE_MAX_UPLOAD_MB?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
