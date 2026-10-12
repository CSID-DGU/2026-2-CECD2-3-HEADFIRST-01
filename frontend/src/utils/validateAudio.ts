import { ACCEPTED_AUDIO_EXTENSIONS, config } from '@/config'
import { getExtension } from './format'

/** 문제가 있으면 에러 메시지, 없으면 null */
export function validateAudioFile(file: File): string | null {
  const ext = getExtension(file.name)
  const isAcceptedExt = (ACCEPTED_AUDIO_EXTENSIONS as readonly string[]).includes(ext)
  const isAudioMime = file.type.startsWith('audio/') || file.type === 'video/webm'

  if (!isAcceptedExt && !isAudioMime) {
    return `지원하지 않는 형식입니다. (${ACCEPTED_AUDIO_EXTENSIONS.join(', ')} 만 가능)`
  }
  if (file.size === 0) {
    return '빈 파일입니다.'
  }
  if (file.size > config.maxUploadMB * 1024 * 1024) {
    return `파일이 너무 큽니다. 최대 ${config.maxUploadMB}MB 까지 업로드할 수 있습니다.`
  }
  return null
}
