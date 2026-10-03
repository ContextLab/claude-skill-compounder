import type { EngineInterface, Register } from 'claude-code'
import { inSubagent, startTurn, turn } from './calls'
import { claimsDone, lastSubstantive, mission, storeRows, substantive, typedByUser, type Row } from './render'

// compound-mission: the user's own requests, stated back verbatim at the moments a session
// tends to lose them. The same five moments hooks/mission.sh had, on the same events, plus
// one the shell could not reach: the compaction itself is told to keep them.
//
//   ambiguity   a prompt too short to stand alone gets the last substantive request
//   resume      after a compaction or a resume
//   dispatch    before an Agent, Task or Workflow call, to the parent
//   subagent    at a subagent's start, to the subagent
//   periodic    on a tool call once INTERVAL seconds have passed since the last delivery
//   completion  once per turn, when a long turn ends on a completion claim
//
// The prompts come from history-surfer's store when it has this session, and otherwise
// from the prompts this process saw submitted. Nothing is copied anywhere else.

const DISPATCH: ReadonlySet<string> = new Set(['Agent', 'Task', 'Workflow'])
const INTERVAL_S = 1200
const STOP_MIN_TOOLS = 8

type Row2 = Record<string, unknown>

function now(): number {
  return Math.floor(Date.now() / 1000)
}

// Module variables start over on a reload; the store is what survives one.
const seen: Row[] = []
// Set when the module loads, so the periodic arm counts from the session's start and a
// session's first tool call is not "due" by default.
let lastDelivery = now()

// A value that is not a short run of digits takes the default: a typo is not a setting.
function numeric(raw: string | undefined, fallback: number): number {
  return raw !== undefined && /^[0-9]{1,9}$/.test(raw) ? Number(raw) : fallback
}

async function off($: EngineInterface): Promise<boolean> {
  return (await $.env.get('COMPOUND_MISSION')) === '0'
}

async function stateDir($: EngineInterface): Promise<string> {
  const set = await $.env.get('SKILL_COMPOUNDER_STATE')
  return set ? `${set}/mod` : `${await $.env.get('HOME')}/.claude/skill-compounder/mod`
}

async function record($: EngineInterface, row: Row2): Promise<void> {
  const line = JSON.stringify({ ts: now(), session: await $.session.id(), ...row })
  await $.process.run(['sh', '-c', 'mkdir -p "$1" && cat >> "$1/mission.jsonl"', 'sh', await stateDir($)], {
    stdin: `${line}\n`,
    timeoutMs: 10000,
  })
}

// history-surfer's file for this project, resolved in the order that project resolves it.
async function storePath($: EngineInterface): Promise<string> {
  const root =
    (await $.env.get('MISSION_SURFER_ROOT')) ||
    (await $.env.get('CLAUDE_HISTORY_SURFER_DIR')) ||
    `${(await $.env.get('CLAUDE_CONFIG_DIR')) || `${await $.env.get('HOME')}/.claude`}/history-surfer`
  const slug = (await $.session.cwd()).replace(/[^A-Za-z0-9]/g, '-')
  return `${root}/projects/${slug}/prompts.jsonl`
}

async function rows($: EngineInterface): Promise<Row[]> {
  const path = await storePath($)
  const stored = (await $.fs.exists(path)) ? storeRows(await $.fs.read(path), await $.session.id()) : []
  return stored.length >= seen.length ? stored : seen
}

async function delivered($: EngineInterface, moment: string, text: string, agent?: string): Promise<void> {
  lastDelivery = now()
  await record($, { moment, agent: agent ?? null, chars: text.length })
}

export const registerMission: Register = on => {
  on('turn.start', async ($, e, next) => {
    const started = await next(e)
    startTurn(started.turnId)
    return started
  })

  on('prompt.submit', async ($, e, next) => {
    const text = e.text.trim()
    if (text === '' || text.startsWith('/') || !typedByUser(text) || (await off($))) return next(e)
    const before = await rows($)
    seen.push({ text })
    if (substantive(text)) return next(e)
    const prior = lastSubstantive(before.filter(r => r.text !== text))
    if (prior === '') return next(e)
    await delivered($, 'ambiguity', prior)
    return next({ ...e, context: [...(e.context ?? []), prior] })
  })

  // What the summary is told to keep. This is an instruction to the summarizer, which is
  // what `instructions` is for, and not text injected into the session.
  on('session.compact', async ($, e, next) => {
    if (e.agentId !== undefined || (await off($))) return next(e)
    const text = mission(await rows($))
    if (text === '') return next(e)
    await delivered($, 'compact', text)
    const keep = `Keep the user's own requests in the summary word for word. They are:\n\n${text}`
    return next({ ...e, instructions: e.instructions ? `${e.instructions}\n\n${keep}` : keep })
  })

  on('classic.SessionStart', async ($, e, next) => {
    const result = await next(e)
    if ((e.source !== 'compact' && e.source !== 'resume') || (await off($))) return result
    const text = mission(await rows($))
    if (text === '') return result
    await delivered($, 'resume', text)
    return { ...result, additionalContext: [...(result.additionalContext ?? []), text] }
  })

  on('classic.SubagentStart', async ($, e, next) => {
    const result = await next(e)
    if (await off($)) return result
    const text = mission(await rows($))
    if (text === '') return result
    const told = `${text}\n\nThe parent's instructions to this agent are above this block.`
    await delivered($, 'subagent', told, e.agent_id)
    return { ...result, additionalContext: [...(result.additionalContext ?? []), told] }
  })

  on('classic.PreToolUse', async ($, e, next) => {
    const result = await next(e)
    // A subagent got the whole mission at its start.
    if (inSubagent.has(e.tool_use_id) || (await off($))) return result
    const dispatch = DISPATCH.has(String(e.tool))
    const due = now() - lastDelivery >= numeric(await $.env.get('COMPOUND_MISSION_INTERVAL'), INTERVAL_S)
    if (!dispatch && !due) return result
    const text = mission(await rows($))
    if (text === '') return result
    await delivered($, dispatch ? 'dispatch' : 'periodic', text)
    return { ...result, additionalContext: [...(result.additionalContext ?? []), text] }
  })

  // Once per turn. `stop_hook_active` is the engine saying this stop follows a block.
  on('classic.Stop', async ($, e, next) => {
    const result = await next(e)
    if (e.stop_hook_active === true || turn.blocked || (await off($))) return result
    if (turn.tools < numeric(await $.env.get('COMPOUND_MISSION_STOP_MIN_TOOLS'), STOP_MIN_TOOLS)) return result
    if (!claimsDone(String(e.last_assistant_message ?? ''))) return result
    const text = mission(await rows($))
    if (text === '') return result
    turn.blocked = true
    const reason = `${text}\n\nThe message that ends this turn is the one the user will read against those requests. This is stated at most once for this turn.`
    await delivered($, 'completion', reason)
    return { ...result, block: reason }
  })
}
