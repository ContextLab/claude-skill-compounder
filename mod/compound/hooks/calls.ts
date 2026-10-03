// What the plugin's one tool.call hook observes on behalf of the mission half. A plugin
// may register one unmatched tool.call hook, and ./lessons owns it; the mission needs two
// facts from the same stream, kept here: how many tool calls the main loop has made since
// the user last typed, and which calls are running inside a subagent right now. No `$`, no I/O.

// Counted from the user's last typed prompt, not per engine turn: a background task's
// notice starts a new turn in the middle of one request, and a count that reset there put
// the completion statement on "waiting for the subagent" and nothing on the real ending.
export const request = { tools: 0, blocked: false }

// Calls now inside a subagent, by tool_use_id. `classic.PreToolUse` carries the call and
// not the loop it runs in; the tool.call hook around it does, and runs first.
export const inSubagent = new Set<string>()

export function startRequest(): void {
  request.tools = 0
  request.blocked = false
}

export function enterCall(toolUseId: string, agentId: string | undefined): void {
  if (agentId === undefined) request.tools += 1
  else inSubagent.add(toolUseId)
}

export function leaveCall(toolUseId: string): void {
  inSubagent.delete(toolUseId)
}
