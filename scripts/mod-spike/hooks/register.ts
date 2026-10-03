import type { Register } from 'claude-code'

// Throwaway probe. Every observation is appended to LOG so a headless run can be read back.
const LOG = '/tmp/compound-spike.log'
let pending: { command: string; error: string } | undefined

async function log($: any, row: Record<string, unknown>) {
  const prior = (await $.fs.exists(LOG)) ? await $.fs.read(LOG) : ''
  await $.fs.write(LOG, prior + JSON.stringify(row) + '\n')
}

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    await log($, { ev: 'session.start', interactive: e.isInteractive })
    return next(e)
  })

  on('prompt.submit', async ($, e, next) => {
    const seen = (await $.session.messages()).filter(m => m.role === 'user').length
    await log($, { ev: 'prompt.submit', text: e.text.slice(0, 80), priorUserMessages: seen })
    return next(e)
  })

  on('tool.call', { tool: 'Bash' }, async ($, e, next) => {
    const ran = await next(e)
    await log($, { ev: 'bash', command: e.command, keys: Object.keys(ran), isError: ran.isError ?? null, deny: ran.deny ?? null, text: String(ran.text ?? '').slice(0, 120) })
    if (ran.deny !== undefined) return ran
    const text = String(ran.text ?? '')
    if (ran.isError === true) {
      pending = { command: e.command, error: text.slice(0, 400) }
      await log($, { ev: 'fail', agentId: e.agentId ?? null, command: e.command })
      return ran
    }
    if (pending === undefined) return ran
    const failed = pending
    pending = undefined
    const r = await $.model.complete({
      model: 'haiku',
      timeoutMs: 20000,
      prompt:
        'A shell command failed and a later one succeeded.\n' +
        `FAILED: ${failed.command}\nERROR: ${failed.error}\nSUCCEEDED: ${e.command}\n\n` +
        'Is the second a fix for the first (same goal, corrected approach)? ' +
        'Answer on one line as: YES <one-sentence reusable lesson>  or  NO <reason>.',
    })
    const verdict = r.isAnswered ? r.text.trim() : `unanswered:${r.reason}`
    await log($, { ev: 'recover', failed: failed.command, worked: e.command, verdict })
    if (!verdict.startsWith('YES')) return ran
    return { ...ran, context: `compound-spike recorded a lesson from this fail-then-fix: ${verdict.slice(4)}` }
  })

  on('turn.complete', async ($, e, next) => {
    await log($, { ev: 'turn.complete', reason: e.reason })
    return next(e)
  })
}
