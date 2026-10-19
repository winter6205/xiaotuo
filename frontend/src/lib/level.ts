const pct = (a: number, b: number) => `${b > 0 ? +Math.min(100, (a / b) * 100).toFixed(2) : 0}%`

/** 等级进度条：(xp − level_min_xp) / (next_level_xp − level_min_xp)；满级 100% */
export const levelPct = (xp: number, l: { level_min_xp: number; next_level_xp: number | null }) =>
  l.next_level_xp == null ? '100%' : pct(Math.max(0, xp - l.level_min_xp), l.next_level_xp - l.level_min_xp)
