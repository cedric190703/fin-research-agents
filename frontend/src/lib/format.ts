export const usd = (n: number) =>
  n.toLocaleString('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 4 })

export const compact = (n: number) => n.toLocaleString('en-US', { notation: 'compact' })

export const UNVERIFIED_PREFIX = '⚠ UNVERIFIED: '

export function isUnverified(claim: string): boolean {
  return claim.startsWith(UNVERIFIED_PREFIX)
}

export function stripUnverified(claim: string): string {
  return isUnverified(claim) ? claim.slice(UNVERIFIED_PREFIX.length) : claim
}

/** Split "text [F1] [Mcompute_ratios.gross_margin.abc]" into text and reference tokens. */
export function splitRefs(claim: string): { text: string; refs: string[] } {
  const refs = [...claim.matchAll(/\[(F\d+|M[^\]]+)\]/g)].map((m) => m[1])
  const text = claim.replace(/\s*\[(F\d+|M[^\]]+)\]/g, '').trim()
  return { text, refs }
}
