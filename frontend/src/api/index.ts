import type { AdminApi } from './adminContract'
import { createHttpAdminApi } from './adminHttp'
import { createMockAdminApi } from './adminMock'
import type { FrybotApi } from './contract'
import { createHttpApi } from './httpApi'
import { createMockApi } from './mockApi'

export * from './adminContract'
export * from './contract'
export { tableName } from './storeLayout'

let shared: FrybotApi | null = null

/**
 * 화면이 쓰는 API 하나를 돌려줍니다.
 * npm run dev:server (VITE_API_MODE=http) 이면 실제 Web Service, npm run dev 면 가짜 API.
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

let sharedAdmin: AdminApi | null = null

/** 관리자 화면(A1~A3)용 API. 가짜 모드에서는 지난 25분을 미리 돌려 둔 가짜 매장 */
export function getAdminApi(): AdminApi {
  sharedAdmin ??= import.meta.env.VITE_API_MODE === 'http' ? createHttpAdminApi() : createMockAdminApi()
  return sharedAdmin
}
