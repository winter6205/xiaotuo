// 学习中心「最近活动」：服务端 recent + 最近一次导入（last_import）生成的汇总，按时间倒序
import type { Dashboard } from './api'

type Recent = Dashboard['recent'][number]
type LastImport = NonNullable<Dashboard['last_import']>
export type Row = ({ type: 'event' } & Recent) | { type: 'import'; at: string; course: Recent['course']; text: string; xp: number }

export function importText(name: string, itemsAdded: number, xpDelta: number): string {
  return `导入了${name}课程进度，新增 ${itemsAdded} 项${xpDelta ? `，+${xpDelta} XP` : ''}`
}

export function activityRows(recent: Recent[], last: Dashboard['last_import'], courseName: (code: string) => string): Row[] {
  const rows: Row[] = recent.map((r) => ({ type: 'event' as const, ...r }))
  if (last) rows.push(importRow(last, courseName(last.course)))
  return rows.sort((a, b) => Date.parse(b.at) - Date.parse(a.at))
}

const importRow = (l: LastImport, name: string): Row =>
  ({ type: 'import', at: l.imported_at, course: l.course, xp: l.xp_delta, text: importText(name, l.items_added, l.xp_delta) })
