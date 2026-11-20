import type { ReactNode } from 'react'
import type { CartLine, Delivery, MenuItem, Order, OrderStage } from '../api'
import c from '../components/customer.module.css'
import { Robot } from '../components/Robot'
import { BellIcon, BrandMark } from '../kiosk/parts'
import { ITEM_STATUS_TEXT, clock, minutesFromNow, subjectJosa, won } from './format'
import s from './table.module.css'

export function TableTopBar(props: {
  tableId: string
  label: string
  arrived?: boolean
  onCallStaff: () => void
}) {
  const { tableId, label, arrived, onCallStaff } = props
  return (
    <div className={`${c.topBar} ${arrived ? s.topBarArrived : ''}`}>
      <BrandMark />
      <span className={c.brand}>OneTeam 레스토랑</span>
      <span className={s.tableBadge}>{tableId} 테이블</span>
      <span className={`${s.screenLabel} ${arrived ? s.screenLabelAccent : ''}`}>{label}</span>
      <button
        type="button"
        className={`${c.staffBtn} ${arrived ? s.staffBtnOnSoft : ''}`}
        onClick={onCallStaff}
      >
        직원 호출
      </button>
    </div>
  )
}

function RobotSide({ bubble, children }: { bubble: string; children: ReactNode }) {
  return (
    <div className={c.robotPanel}>
      <div className={`${c.bubble} ${s.panelBubble}`}>{bubble}</div>
      {children}
    </div>
  )
}

/* T1 메뉴 선택 (SR-009·010) */
export function T1Menu(props: {
  menu: MenuItem[] | null
  cart: CartLine[]
  hasOrders: boolean
  onChange: (menuId: string, qty: number) => void
  onNext: () => void
  onStatus: () => void
}) {
  const { menu, cart, hasOrders, onChange, onNext, onStatus } = props
  const qtyOf = (id: string) => cart.find((l) => l.menuId === id)?.qty ?? 0
  const count = cart.reduce((n, l) => n + l.qty, 0)
  const total = cart.reduce((n, l) => n + l.qty * (menu?.find((m) => m.menuId === l.menuId)?.price ?? 0), 0)

  return (
    <>
      <div className={`${s.main} ${s.mainMenu}`}>
        <div className={`${s.col} ${s.menuArea}`}>
          <h1 className={s.title36}>무엇을 드실래요?</h1>
          {!menu && <div className={s.note16}>메뉴를 불러오는 중…</div>}
          <div className={s.menuGrid}>
            {menu?.map((m) => {
              const q = qtyOf(m.menuId)
              return (
                <div key={m.menuId} className={s.menuCard}>
                  <div
                    className={s.menuPhoto}
                    style={m.imageUrl ? { backgroundImage: `url(${m.imageUrl})` } : undefined}
                  >
                    {!m.imageUrl && '메뉴 사진'}
                  </div>
                  <div className={s.menuInfo}>
                    <b>{m.name}</b>
                    <span>{won(m.price)}</span>
                  </div>
                  <div className={s.stepper}>
                    <button
                      type="button"
                      className={s.stepBtn}
                      aria-label={`${m.name} 빼기`}
                      disabled={q === 0}
                      onClick={() => onChange(m.menuId, q - 1)}
                    >
                      −
                    </button>
                    <b aria-label={`${m.name} ${q}개`}>{q}</b>
                    <button
                      type="button"
                      className={`${s.stepBtn} ${s.stepBtnPlus}`}
                      aria-label={`${m.name} 더하기`}
                      onClick={() => onChange(m.menuId, q + 1)}
                    >
                      +
                    </button>
                  </div>
                </div>
              )
            })}
          </div>
        </div>
        <RobotSide bubble="골라 주세요!">
          <Robot pose="wave" width={170} height={204} />
        </RobotSide>
      </div>
      <div className={s.footer}>
        <div className={s.cartSummary}>
          <span>담은 메뉴 {count}개</span>
          <b>{won(total)}</b>
        </div>
        <div className={s.footerBtns}>
          {hasOrders && (
            <button type="button" className={c.secondaryBtn} style={{ height: 72 }} onClick={onStatus}>
              주문 현황
            </button>
          )}
          <button
            type="button"
            className={`${c.primaryBtn} ${s.btn72}`}
            style={{ width: 360 }}
            disabled={count === 0}
            onClick={onNext}
          >
            주문 확인
          </button>
        </div>
      </div>
    </>
  )
}

/* T2 주문 확인 · 확정 (SR-011·012) */
export function T2Confirm(props: {
  tableId: string
  menu: MenuItem[]
  cart: CartLine[]
  busy: boolean
  error: string | null
  onEdit: () => void
  onPlace: () => void
}) {
  const { tableId, menu, cart, busy, error, onEdit, onPlace } = props
  const lines = cart
    .filter((l) => l.qty > 0)
    .map((l) => ({ ...l, item: menu.find((m) => m.menuId === l.menuId)! }))
    .filter((l) => l.item)
  const total = lines.reduce((n, l) => n + l.qty * l.item.price, 0)

  return (
    <>
      <div className={s.main}>
        <div className={s.col} style={{ gap: 18 }}>
          <h1 className={s.title36}>이대로 주문할까요?</h1>
          <div className={s.receipt}>
            {lines.map((l) => (
              <div key={l.menuId} className={s.receiptRow}>
                <span>
                  {l.item.name} <span className={s.muted}>× {l.qty}</span>
                </span>
                <b>{won(l.qty * l.item.price)}</b>
              </div>
            ))}
            <div className={s.divider} />
            <div className={`${s.receiptRow} ${s.receiptRowSmall}`}>
              <span className={s.muted}>받는 테이블</span>
              <b>{tableId}</b>
            </div>
            <div className={s.receiptTotal}>
              <span>합계</span>
              <b>{won(total)}</b>
            </div>
          </div>
          {error && (
            <div className={s.error} role="alert">
              {error}
            </div>
          )}
        </div>
        <RobotSide bubble="확인해 주세요">
          <Robot pose="confirm" width={180} height={216} />
        </RobotSide>
      </div>
      <div className={s.footer}>
        <button type="button" className={s.btnSide} onClick={onEdit} disabled={busy}>
          수정
        </button>
        <button
          type="button"
          className={`${c.primaryBtn} ${s.btn72}`}
          style={{ flexGrow: 1, width: 'auto' }}
          disabled={busy}
          onClick={onPlace}
        >
          {busy ? '주문 보내는 중…' : '주문하기'}
        </button>
      </div>
    </>
  )
}

const STAGES: { key: OrderStage; label: string }[] = [
  { key: 'received', label: '접수' },
  { key: 'cooking', label: '조리 중' },
  { key: 'serving', label: '서빙' },
  { key: 'done', label: '완료' },
]

function StageTrack({ stage }: { stage: OrderStage }) {
  const now = STAGES.findIndex((x) => x.key === stage)
  const allDone = stage === 'done'
  return (
    <ol className={s.stages} aria-label="주문 진행 단계">
      {STAGES.map((st, i) => {
        const done = i < now || allDone
        const current = i === now && !allDone
        return (
          <li key={st.key} style={{ display: 'contents' }}>
            {i > 0 && <span className={`${s.stageLine} ${i <= now ? s.stageLineOn : ''}`} aria-hidden="true" />}
            <span
              className={`${s.stage} ${done ? s.stageDone : ''} ${current ? s.stageNow : ''}`}
              aria-current={current ? 'step' : undefined}
            >
              <span className={s.stageDot}>
                {done && (
                  <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true">
                    <path
                      d="M3.5 8.2 l3 3 L12.5 5"
                      stroke="#FFFFFF"
                      strokeWidth="2.4"
                      fill="none"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                  </svg>
                )}
                {current && <span className={s.stageNowCore} />}
              </span>
              <span>{st.label}</span>
            </span>
          </li>
        )
      })}
    </ol>
  )
}

/* T3 진행 상태 (SR-013·015) */
export function T3Status(props: {
  order: Order
  now: Date
  onMore: () => void
  onEnd: () => void
}) {
  const { order, now, onMore, onEnd } = props
  const done = order.stage === 'done'
  return (
    <>
      <div className={s.main}>
        <div className={s.col} style={{ gap: 20 }}>
          <div className={s.col} style={{ gap: 4 }}>
            <span className={s.etaLabel}>{done ? '주문 상태' : '도착 예정'}</span>
            <div className={s.etaRow}>
              <span className={s.etaTime}>{done ? '전달 완료' : order.etaAt ? clock(order.etaAt) : '-'}</span>
              {!done && order.etaAt && <span className={s.etaIn}>{minutesFromNow(order.etaAt, now)}</span>}
            </div>
          </div>
          <StageTrack stage={order.stage} />
          <div className={s.itemList}>
            {order.items.map((it) => {
              const st = ITEM_STATUS_TEXT[it.status]
              return (
                <div key={it.menuId} className={s.itemRow}>
                  <span>
                    {it.name} {it.qty}
                  </span>
                  <span className={`${s.itemStatus} ${st.accent ? s.itemStatusAccent : ''}`}>{st.text}</span>
                </div>
              )
            })}
          </div>
        </div>
        <RobotSide bubble={done ? '맛있게 드세요!' : '맛있게 만드는 중!'}>
          <Robot pose="cook" width={180} height={216} />
        </RobotSide>
      </div>
      <div className={s.footer}>
        <span className={s.note15}>도착 예정 시각은 조리 상황에 따라 조금 바뀔 수 있어요</span>
        <div className={s.footerBtns}>
          <button type="button" className={c.secondaryBtn} onClick={onEnd}>
            이용 종료
          </button>
          <button type="button" className={c.secondaryBtn} onClick={onMore}>
            추가 주문
          </button>
        </div>
      </div>
    </>
  )
}

const DELIVERY_STEPS: { key: Delivery['step']; label: string }[] = [
  { key: 'arrived', label: '서빙 로봇 도착 · 정차 확인' },
  { key: 'transferring', label: '테이블로 옮기는 중' },
  { key: 'done', label: '전달 완료' },
]

/* T4 음식 도착 안내 (SR-024·025·026) */
export function T4Arrived({ delivery }: { delivery: Delivery }) {
  const names = delivery.itemNames.join(', ')
  const now = DELIVERY_STEPS.findIndex((x) => x.key === delivery.step)
  return (
    <>
      <div className={`${s.main} ${s.mainArrived}`}>
        <div className={s.col} style={{ gap: 20 }}>
          <h1 className={s.title44}>
            <span className={s.accent}>{names}</span>
            {subjectJosa(names)}
            <br />
            도착했어요
          </h1>
          <div className={s.warn} role="note">
            <svg width="22" height="22" viewBox="0 0 24 24" aria-hidden="true">
              <path d="M12 3 L22 20 H2z" fill="#F5B300" />
              <rect x="11" y="9" width="2" height="6" rx="1" fill="#FFFFFF" />
              <circle cx="12" cy="17.2" r="1.2" fill="#FFFFFF" />
            </svg>
            로봇팔이 옮기는 동안 손을 넣지 말아 주세요
          </div>
          <ol className={s.deliverySteps} aria-label="전달 진행">
            {DELIVERY_STEPS.map((st, i) => {
              const done = i < now || delivery.step === 'done'
              const current = i === now && delivery.step !== 'done'
              return (
                <li
                  key={st.key}
                  className={`${s.deliveryStep} ${done ? s.deliveryDone : ''} ${current ? s.deliveryNow : ''}`}
                  aria-current={current ? 'step' : undefined}
                >
                  <span className={s.deliveryDot} />
                  {st.label}
                </li>
              )
            })}
          </ol>
        </div>
        <RobotSide bubble="맛있게 드세요!">
          <Robot pose="serve" width={200} height={240} />
        </RobotSide>
      </div>
      <div className={s.footer}>
        <BellIcon />
        <span className={s.note16}>
          도착하면 이 화면으로 바뀌고 알림음이 울려요 · 전달이 끝나면 진행 상태 화면으로 돌아가요
        </span>
      </div>
    </>
  )
}

/* T5 이용 종료 확인 (SR-027·028) */
export function T5EndDialog(props: { busy: boolean; onKeep: () => void; onEnd: () => void }) {
  const { busy, onKeep, onEnd } = props
  return (
    <div className={s.dim}>
      <div className={s.dialog} role="dialog" aria-modal="true" aria-labelledby="t5-title">
        <Robot pose="wave" width={110} height={132} />
        <h2 id="t5-title" className={s.dialogTitle}>
          이용을 마칠까요?
        </h2>
        <div className={s.dialogBody}>
          종료하면 이 테이블은 정리 후 다음 손님에게 배정돼요.
          <br />
          종료 뒤에는 추가 주문을 할 수 없어요.
        </div>
        <div className={s.dialogBtns}>
          <button type="button" className={s.dialogKeep} onClick={onKeep} disabled={busy}>
            계속 이용
          </button>
          <button type="button" className={s.dialogEnd} onClick={onEnd} disabled={busy}>
            이용 종료
          </button>
        </div>
      </div>
    </div>
  )
}

/** 이용 종료 뒤 화면 — 시안에 없어 고객 화면 규칙에 맞춰 추가 */
export function TableEnded() {
  return (
    <div className={s.ended}>
      <Robot pose="wave" width={170} height={204} />
      <h1 className={s.title36}>이용해 주셔서 고마워요</h1>
      <div className={s.note16}>직원이 자리를 정리해 드릴게요. 안녕히 가세요!</div>
    </div>
  )
}
