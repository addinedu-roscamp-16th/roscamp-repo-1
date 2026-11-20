import { tableName, type GuideProgress } from '../api'
import { Robot } from '../components/Robot'
import { StoreMap } from '../components/StoreMap'
import c from '../components/customer.module.css'
import s from './kiosk.module.css'
import { PARTY_SIZES, formatEta, type PartySize, type Seat } from './format'
import { BellIcon, CheckIcon, ProgressBar, RobotPanel } from './parts'

/* K1 인원 선택 (SR-001) */
export function K1PartySize(props: {
  selected: PartySize | null
  busy: boolean
  error: string | null
  onSelect: (n: PartySize) => void
  onSubmit: () => void
}) {
  const { selected, busy, error, onSelect, onSubmit } = props
  return (
    <>
      <div className={s.main}>
        <div className={s.col} style={{ gap: 28 }}>
          <div className={s.col} style={{ gap: 10 }}>
            <h1 className={s.title40} style={{ margin: 0 }}>몇 분이 오셨나요?</h1>
            <div className={s.sub}>인원에 맞는 자리를 바로 찾아 드릴게요</div>
          </div>
          <div className={s.partyGrid}>
            {PARTY_SIZES.map((n) => (
              <button
                key={n}
                type="button"
                className={s.partyBtn}
                aria-label={`${n}명`}
                aria-pressed={selected === n}
                onClick={() => onSelect(n)}
              >
                <span className={s.partyNum}>{n}</span>
                <span className={s.partyUnit}>명</span>
              </button>
            ))}
          </div>
          {error ? (
            <div className={s.error} role="alert">{error}</div>
          ) : (
            <div className={s.hint}>
              5명 이상이면 오른쪽 위 <b>직원 호출</b>을 눌러 주세요
            </div>
          )}
        </div>
        <RobotPanel bubble="반가워요!">
          <Robot pose="wave" />
        </RobotPanel>
      </div>
      <div className={s.footer}>
        <button type="button" className={c.primaryBtn} disabled={!selected || busy} onClick={onSubmit}>
          {busy ? '자리 찾는 중…' : selected ? `${selected}명으로 자리 찾기` : '인원을 골라 주세요'}
        </button>
      </div>
    </>
  )
}

/* K2 테이블 배정 결과 (SR-002·003·004·005) */
export function K2TableAssigned(props: {
  assignment: Seat
  guide: GuideProgress | null
  onHome: () => void
}) {
  const { assignment: a, guide, onHome } = props
  return (
    <>
      <div className={`${s.main} ${s.mainWide}`}>
        <div className={s.col} style={{ gap: 20 }}>
          <div className={s.eyebrow}>자리를 찾았어요</div>
          <h1 className={s.title44} style={{ margin: 0 }}>
            <span className={s.accent}>{tableName(a.tableId)}</span> 테이블로
            <br />
            모실게요
          </h1>
          <div className={s.chips}>
            <span className={s.chip}>{a.seats}인석</span>
            <span className={s.chip}>{a.partySize}명</span>
          </div>
          <div className={s.robotCard}>
            <Robot pose="peek" />
            <div className={s.robotCardBody}>
              <div className={s.robotCardHead}>
                <b>안내 로봇이 오고 있어요</b>
                {guide?.eta_sec != null && <span>{formatEta(guide.eta_sec)}</span>}
              </div>
              <ProgressBar value={guide?.progress ?? 0} label="안내 로봇 도착 진행률" />
            </div>
          </div>
        </div>
        <div className={s.mapPanel}>
          <StoreMap tableId={a.tableId} />
        </div>
      </div>
      <div className={s.footer}>
        <span className={s.footerNote}>로봇이 오면 다음 화면으로 자동으로 넘어가요</span>
        <button type="button" className={c.secondaryBtn} onClick={onHome}>
          처음으로
        </button>
      </div>
    </>
  )
}

/* K3 안내 로봇 대기 — 예외 (SR-005) */
export function K3RobotWaiting(props: {
  assignment: Seat
  guide: GuideProgress | null
  onHome: () => void
}) {
  const { assignment: a, guide, onHome } = props
  const position =
    guide?.state === 'PENDING' && guide.queue_position != null ? `${guide.queue_position}번째` : '곧 도착'
  const eta = guide?.eta_sec != null ? formatEta(guide.eta_sec) : '-'
  return (
    <>
      <div className={s.main}>
        <div className={s.col} style={{ gap: 24 }}>
          <div className={s.okBadge}>
            <CheckIcon />
            {tableName(a.tableId)} 테이블은 맡아 두었어요
          </div>
          <h1 className={s.title40} style={{ margin: 0, lineHeight: 1.3 }}>
            로봇이 모두 안내 중이에요
            <br />
            조금만 기다려 주세요
          </h1>
          <div className={s.statGrid}>
            <div className={s.stat}>
              <span>대기 순번</span>
              <b>{position}</b>
            </div>
            <div className={s.stat}>
              <span>예상 대기</span>
              <b>{eta}</b>
            </div>
          </div>
        </div>
        <RobotPanel bubble="금방 갈게요!">
          <Robot pose="wait" />
        </RobotPanel>
      </div>
      <div className={s.footer} style={{ gap: 12 }}>
        <BellIcon />
        <span className={s.footerNote}>로봇이 도착하면 화면과 소리로 알려 드려요</span>
        <button type="button" className={c.secondaryBtn} onClick={onHome}>
          처음으로
        </button>
      </div>
    </>
  )
}

/* K4 안내 시작 (SR-006·007) */
export function K4GuideStart(props: {
  assignment: Seat
  secondsLeft: number
  totalSeconds: number
  onHome: () => void
}) {
  const { assignment: a, secondsLeft, totalSeconds, onHome } = props
  return (
    <>
      <div className={s.main}>
        <div className={s.col} style={{ gap: 22 }}>
          <div className={s.eyebrow}>로봇이 도착했어요</div>
          <h1 className={s.title44} style={{ margin: 0 }}>
            로봇을 따라
            <br />
            <span className={s.accent}>{tableName(a.tableId)}</span> 테이블로 가세요
          </h1>
          <div className={s.guideSteps}>
            <div className={s.guideStep}>
              <span className={s.guideNum}>1</span>
              <span>
                로봇 화면에 <b>{tableName(a.tableId)}</b>이 떠 있는 로봇이에요
              </span>
            </div>
            <div className={s.guideStep}>
              <span className={s.guideNum}>2</span>
              <span>
                로봇과 <b>1~2m</b> 거리를 지켜 주세요. 멀어지면 로봇이 기다려요
              </span>
            </div>
          </div>
        </div>
        <RobotPanel bubble="저를 따라오세요!">
          <Robot pose="guide" label={tableName(a.tableId)} />
        </RobotPanel>
      </div>
      <div className={s.footer} style={{ gap: 20 }}>
        <div className={s.col} style={{ flexGrow: 1, gap: 8 }}>
          <span className={s.footerNote}>{secondsLeft}초 뒤 첫 화면으로 돌아가요</span>
          <ProgressBar value={secondsLeft / totalSeconds} muted label="첫 화면으로 돌아가기까지 남은 시간" />
        </div>
        <button type="button" className={c.secondaryBtn} style={{ marginLeft: 0 }} onClick={onHome}>
          처음으로
        </button>
      </div>
    </>
  )
}
