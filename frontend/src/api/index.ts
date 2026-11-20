import type { FrybotApi } from './contract'
import { createHttpApi } from './httpApi'
import { createMockApi } from './mockApi'

export * from './contract'
export { tableName } from './storeLayout'

let shared: FrybotApi | null = null

/**
 * 화면이 쓰는 API 하나를 돌려줍니다.
 * VITE_API_MODE=http 이면 실제 Web Service, 아니면 가짜 API.
 * 가짜 API는 한 브라우저 탭 안에서 키오스크·태블릿이 같은 매장 상태를 공유합니다.
 * 가짜 모드에서 주소 뒤에 ?robot=busy 를 붙이면 안내 로봇 대기(K3) 흐름을 볼 수 있습니다.
 */
export function getApi(): FrybotApi {
  if (shared) return shared
  if (import.meta.env.VITE_API_MODE === 'http') {
    shared = createHttpApi()
  } else {
    const params = new URLSearchParams(window.location.search)
    shared = createMockApi({ robotAvailable: params.get('robot') !== 'busy', autoSeat: true })
  }
  return shared
}
