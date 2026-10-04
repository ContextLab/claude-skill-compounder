import type { Register } from 'claude-code'
import { fixPrompt, parseFix } from '../../../../hooks/judge'
import { parseInventory } from '../../../../hooks/store'

// The fix judge, asked for real. tests/journeys/measure_fix.py copies this file and the
// mod's own judge.ts, safe.ts and store.ts into one directory (and points the two imports
// above at the copies), so the prompt and the reading of the
// reply are the mod's, and the question goes through `$.model.complete` with the request
// the mod sends. COMPOUND_FIX_PROBE names a directory: `asks.json` holds the pairs and the
// model, `lessons.json` what `compound list --scripts --json` printed, and `replies.json`
// is written with one row for every question.

type Ask = { id: string; failed: string; error: string; worked: string; between?: string[] }
type Asks = { model: string; timeoutMs: number; asks: Ask[] }
const TOGETHER = 4

export const register: Register = on => {
  on('prompt.submit', async ($, e, next) => {
    const dir = await $.env.get('COMPOUND_FIX_PROBE')
    if (!dir) return next(e)
    try {
      const asked = JSON.parse(await $.fs.read(`${dir}/asks.json`)) as Asks
      const lessons = (parseInventory(await $.fs.read(`${dir}/lessons.json`)) ?? []).filter(i => i.kind === 'lesson')
      const rows: Record<string, unknown>[] = []
      const one = async (a: Ask): Promise<void> => {
        // An older judge.ts takes no `between` and ignores it.
        const pair = { failed: a.failed, error: a.error, worked: a.worked, between: a.between ?? [] }
        const prompt = fixPrompt(pair as Parameters<typeof fixPrompt>[0], lessons)
        const began = Date.now()
        const r = await $.model.complete({ model: asked.model, prompt, timeoutMs: asked.timeoutMs, maxTokens: 400 })
        const ms = Date.now() - began
        if (!r.isAnswered) {
          rows.push({ id: a.id, ms, verdict: 'unanswered', reason: r.reason })
          return
        }
        const answer = parseFix(r.text, lessons, a.error)
        rows.push({
          id: a.id,
          ms,
          verdict: answer === undefined ? 'unreadable' : answer.verdict,
          reason: answer?.verdict === 'NONE' ? answer.reason : '',
          text: r.text,
          chars: prompt.length,
        })
      }
      for (let i = 0; i < asked.asks.length; i += TOGETHER) await Promise.all(asked.asks.slice(i, i + TOGETHER).map(one))
      await $.fs.write(`${dir}/replies.json`, JSON.stringify({ lessons: lessons.map(l => l.name), rows }))
    } catch (err) {
      await $.fs.write(`${dir}/replies.json`, JSON.stringify({ problem: err instanceof Error ? `${err.name}: ${err.message}` : String(err) }))
    }
    return next(e)
  }).catch(($, e, next) => next(e))
}
