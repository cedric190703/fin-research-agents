import { isUnverified, splitRefs, stripUnverified, usd } from './format'

describe('format helpers', () => {
  it('detects and strips the unverified marker', () => {
    expect(isUnverified('⚠ UNVERIFIED: x')).toBe(true)
    expect(isUnverified('x')).toBe(false)
    expect(stripUnverified('⚠ UNVERIFIED: x')).toBe('x')
    expect(stripUnverified('x')).toBe('x')
  })

  it('splits finding and metric references from claim text', () => {
    const { text, refs } = splitRefs('Margin was 45%. [F1] [Mcompute_ratios.gross_margin.abc]')
    expect(text).toBe('Margin was 45%.')
    expect(refs).toEqual(['F1', 'Mcompute_ratios.gross_margin.abc'])
    expect(splitRefs('no refs')).toEqual({ text: 'no refs', refs: [] })
  })

  it('formats usd with up to four decimals', () => {
    expect(usd(0.4321)).toBe('$0.4321')
    expect(usd(12)).toBe('$12.00')
  })
})
