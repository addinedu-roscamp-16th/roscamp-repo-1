import { createHttpKioskApi } from './httpKioskApi'
import { createHttpTableApi } from './httpTableApi'
import { createMockKioskApi } from './mockKioskApi'
import { createMockTableApi } from './mockTableApi'
import type { TableApi } from './tableTypes'
import type { KioskApi } from './types'

export * from './tableTypes'
export * from './types'

const isHttpMode = () => import.meta.env.VITE_API_MODE === 'http'

/**
 * VITE_API_MODE=http 이면 실제 백엔드, 아니면 가짜 API를 씁니다.
 * 가짜 모드에서 주소 뒤에 ?robot=busy 를 붙이면 로봇 대기(K3) 흐름을 볼 수 있습니다.
 */
export function createKioskApi(): KioskApi {
  if (isHttpMode()) return createHttpKioskApi()
  const params = new URLSearchParams(window.location.search)
  return createMockKioskApi({ robotAvailable: params.get('robot') !== 'busy' })
}

export function createTableApi(): TableApi {
  return isHttpMode() ? createHttpTableApi() : createMockTableApi()
}
