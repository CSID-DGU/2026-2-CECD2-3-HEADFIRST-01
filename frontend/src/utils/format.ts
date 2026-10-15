export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 ** 2).toFixed(1)} MB`
}

/** 초 → "m:ss" */
export function formatDuration(seconds: number | null | undefined): string {
  if (seconds == null || !Number.isFinite(seconds)) return '-'
  const m = Math.floor(seconds / 60)
  const s = Math.floor(seconds % 60)
  return `${m}:${s.toString().padStart(2, '0')}`
}

export function formatPercent(value: number): string {
  return `${Math.round(value * 100)}%`
}

export function getExtension(fileName: string): string {
  const idx = fileName.lastIndexOf('.')
  return idx < 0 ? '' : fileName.slice(idx).toLowerCase()
}
