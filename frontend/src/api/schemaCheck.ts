import Ajv2020, { type ErrorObject } from 'ajv/dist/2020'
import addFormats from 'ajv-formats'
import { parse } from 'yaml'
import specText from '../../../api/openapi.yaml?raw'

/**
 * api/openapi.yaml 의 스키마로 데이터 모양을 검사합니다 (계약 테스트, /check 화면).
 * 반환: 틀린 곳 목록. 비어 있으면 모양이 맞음.
 */
const spec = parse(specText) as { components: { schemas: Record<string, unknown> } }

const ajv = new Ajv2020({ strict: false, allErrors: true })
addFormats(ajv)
ajv.addSchema({ $id: 'openapi', components: spec.components })

export type SchemaName = keyof typeof spec.components.schemas & string

function explain(e: ErrorObject, prefix: string): string {
  // 예: prefix "[0]" + "/items/1/qty" → "[0].items.1.qty"
  const where = (prefix + e.instancePath.replace(/\//g, '.')).replace(/^\./, '')
  const at = where ? `${where}: ` : ''
  const p = e.params as Record<string, unknown>
  switch (e.keyword) {
    case 'required':
      return `${where ? `${where}.` : ''}${String(p.missingProperty)} 칸이 빠졌어요`
    case 'enum':
      return `${at}허용되지 않는 값이에요 (${(p.allowedValues as unknown[]).join(', ')} 중 하나)`
    case 'const':
      return `${at}${JSON.stringify(p.allowedValue)} 이어야 해요`
    case 'type':
      return `${at}타입이 달라요 (${String(p.type)} 이어야 해요)`
    case 'format':
      return `${at}형식이 달라요 (${String(p.format)}, 예 2026-11-20T07:00:00Z)`
    default:
      return `${at}${e.message ?? '모양이 달라요'}`
  }
}

/** 같은 곳의 oneOf·anyOf 갈래 오류는 한 번만 */
function summarize(errors: ErrorObject[], prefix: string) {
  const out: string[] = []
  for (const e of errors) {
    if (e.keyword === 'oneOf' || e.keyword === 'anyOf' || e.keyword === 'if') continue
    const m = explain(e, prefix)
    if (!out.includes(m)) out.push(m)
  }
  return out
}

export function checkShape(name: string, data: unknown, prefix = ''): string[] {
  const validate = ajv.getSchema(`openapi#/components/schemas/${name}`)
  if (!validate) throw new Error(`openapi.yaml 에 ${name} 스키마가 없어요`)
  if (validate(data)) return []
  return summarize(validate.errors ?? [], prefix).slice(0, 5)
}

/** 목록의 각 항목을 검사 */
export function checkList(name: string, data: unknown): string[] {
  if (!Array.isArray(data)) return ['목록([...])이어야 해요']
  return data.flatMap((d, i) => checkShape(name, d, `[${i}]`)).slice(0, 5)
}
