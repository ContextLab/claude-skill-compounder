#!/usr/bin/env bash
# What is still in flight that a turn is about to walk away from?
# Prints each kind of unattended work; exit 1 when anything is found, 0 when clear.
found=0
# 1. Long-lived processes detached from a shell (nohup'd runs, background suites).
procs=$(ps -eo pid=,etime=,command= 2>/dev/null | grep -E 'pytest|nohup|run_in_background|canary|python .*-m ' | grep -vE 'grep|inflight-check' | head -8)
if [ -n "$procs" ]; then found=1; echo "PROCESSES still running:"; echo "$procs" | cut -c1-150; fi
# 2. Hosted runs in progress in this repository, and my open PRs with pending checks.
if command -v gh >/dev/null 2>&1 && git rev-parse --git-dir >/dev/null 2>&1; then
  runs=$(gh run list --status in_progress --limit 8 --json databaseId,workflowName,createdAt \
         --jq '.[]|"\(.databaseId) \(.workflowName) since \(.createdAt)"' 2>/dev/null)
  if [ -n "$runs" ]; then found=1; echo "HOSTED RUNS in progress:"; echo "$runs"; fi
  for n in $(gh pr list --author @me --state open --json number --jq '.[].number' 2>/dev/null); do
    pending=$(gh pr checks "$n" --json state --jq '[.[]|select(.state=="IN_PROGRESS" or .state=="QUEUED" or .state=="PENDING")]|length' 2>/dev/null)
    if [ "${pending:-0}" != "0" ]; then found=1; echo "PR #$n has $pending check(s) still pending"; fi
  done
fi
[ $found -eq 0 ] && echo "nothing in flight"
exit $found
