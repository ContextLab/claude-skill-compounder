import { expect, test } from 'claude-code/testing'
import { DEFAULTS, DEFAULT_MODEL, isOff, isQuiet, knobsFrom, modelName, whole } from './knobs'

test('with nothing set every knob is its default', async () => {
  expect(knobsFrom({})).toEqual(DEFAULTS)
  expect(DEFAULTS).toEqual({ promptMinChars: 80, turnMinCalls: 25, nudgeCooldown: 1800, recurLimit: 2, model: DEFAULT_MODEL, judgeTimeoutMs: 10000, repeatMin: 3 })
})

test('a well-formed value is taken', async () => {
  const k = knobsFrom({ promptMinChars: '0', turnMinCalls: '3', nudgeCooldown: '0', recurLimit: '5', model: 'sonnet', judgeTimeout: '4' })
  expect(k).toEqual({ promptMinChars: 0, turnMinCalls: 3, nudgeCooldown: 0, recurLimit: 5, model: 'sonnet', judgeTimeoutMs: 4000, repeatMin: 3 })
})

test('a value of the wrong shape takes the default, never a guess', async () => {
  for (const bad of ['', ' 5', '5 ', '-1', '1.5', '1e3', 'ten', '0x10', '1234567890']) {
    expect(whole(bad, 42)).toBe(42)
  }
  expect(whole(undefined, 42)).toBe(42)
  expect(whole('007', 42)).toBe(7)
})

test('a knob that cannot be zero takes its default at zero', async () => {
  const k = knobsFrom({ turnMinCalls: '0', recurLimit: '0', judgeTimeout: '0' })
  expect(k.turnMinCalls).toBe(25)
  expect(k.recurLimit).toBe(2)
  expect(k.judgeTimeoutMs).toBe(10000)
})

test('a model name is an alias or an id, and anything else is the default', async () => {
  expect(modelName('claude-haiku-4-5-20251001')).toBe('claude-haiku-4-5-20251001')
  expect(modelName('opus[1m]')).toBe('opus[1m]')
  expect(modelName('')).toBe(DEFAULT_MODEL)
  expect(modelName('sonnet; rm -rf /')).toBe(DEFAULT_MODEL)
  expect(modelName('x'.repeat(200))).toBe(DEFAULT_MODEL)
  expect(modelName(undefined)).toBe(DEFAULT_MODEL)
})

test('only the literal 1 turns the band off', async () => {
  expect(isQuiet('1')).toBe(true)
  for (const raw of [undefined, '', '0', 'true', 'yes', ' 1', '11']) expect(isQuiet(raw)).toBe(false)
})

test('only the literal 1 switches the mod off', async () => {
  expect(isOff('1')).toBe(true)
  for (const v of [undefined, '', '0', 'true', 'yes', ' 1']) expect(isOff(v)).toBe(false)
})

test('how many sessions make a request one that keeps coming back: three, never fewer than two', async () => {
  expect(knobsFrom({}).repeatMin).toBe(3)
  expect(knobsFrom({ repeatMin: '5' }).repeatMin).toBe(5)
  expect(knobsFrom({ repeatMin: '2' }).repeatMin).toBe(2)
  for (const bad of ['1', '0', 'many', '-3', '2.5']) expect(knobsFrom({ repeatMin: bad }).repeatMin).toBe(3)
})
