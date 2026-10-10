#!/usr/bin/env bash
# Stop hook: refuse to end a turn that leaves work in flight with nothing watching it.
# Blocks at most once per stop (stop_hook_active), and only for work that is plausibly
# this user's own: detached processes, runs they dispatched, their PRs with pending checks.
input=$(cat)
[ "$(printf '%s' "$input" | jq -r '.stop_hook_active // false' 2>/dev/null)" = "true" ] && exit 0

items=""
# 1. Detached processes (reparented to init) that look like a test suite or a Claude-launched job.
procs=$(ps -eo ppid=,pid=,etime=,command= 2>/dev/null \
  | awk '$1==1' | grep -E 'pytest|/claude-[0-9]+/|nohup' | grep -vE 'grep|inflight-stop-check' \
  | awk '{printf "pid %s (up %s) %s\n", $2, $3, substr($0, index($0,$4), 110)}' | head -6)
[ -n "$procs" ] && items="${items}DETACHED PROCESSES:\n${procs}\n"

if command -v gh >/dev/null 2>&1 && git rev-parse --git-dir >/dev/null 2>&1; then
  # 2. Workflow runs I dispatched by hand that are still going (cron runs are not mine to watch).
  me=$(gh api user --jq .login 2>/dev/null)   # "@me" is not accepted by `gh run list --user`
  runs=$(gh run list --user "$me" --event workflow_dispatch --status in_progress --limit 6 \
         --json databaseId,workflowName --jq '.[]|"run \(.databaseId) \(.workflowName)"' 2>/dev/null)
  [ -n "$runs" ] && items="${items}DISPATCHED RUNS IN PROGRESS:\n${runs}\n"
  # 3. My open PRs with checks still pending.
  for n in $(gh pr list --author @me --state open --limit 10 --json number --jq '.[].number' 2>/dev/null); do
    p=$(gh pr checks "$n" --json state --jq '[.[]|select(.state=="IN_PROGRESS" or .state=="QUEUED" or .state=="PENDING")]|length' 2>/dev/null)
    [ "${p:-0}" != "0" ] && items="${items}PR #$n: $p check(s) pending\n"
  done
fi
[ -z "$items" ] && exit 0

# A waiter is a live polling loop: a shell whose command sleeps AND polls gh / a pid / a log.
waiters=$(ps -eo command= 2>/dev/null | grep -E 'sleep [0-9]+' \
  | grep -E 'gh (run|pr) |ps -p|pgrep|grep -q' | grep -vE 'inflight-stop-check' | grep -vc '^grep')
[ "${waiters:-0}" -gt 0 ] && exit 0

reason=$(printf 'Work is still in flight and NO waiter is running:\n%b\nBefore stopping, either start a background waiter (run_in_background) that exits when these finish, with a deadline, or say plainly in the final message that nobody is watching them and when to look.' "$items")
jq -n --arg r "$reason" '{decision:"block", reason:$r}'
