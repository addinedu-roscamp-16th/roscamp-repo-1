/** 30 → "약 30초", 90 → "약 2분" */
export function formatEta(sec: number) {
  if (sec < 60) return `약 ${Math.max(1, Math.round(sec))}초`
  return `약 ${Math.round(sec / 60)}분`
}
