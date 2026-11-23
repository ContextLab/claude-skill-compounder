---
name: verify-transient-before-waiting
description: Use when a failure looks transient or flaky (a network, DNS, timeout or resource error; CI that fails in setup; 'temporary failure', 'connection reset', 'rate limited') and the plan is to rerun, retry or wait it out, or to tell the user it is not our problem.
created: 2026-11-11
---
Treat a failure as transient only after it has passed. "Temporary failure", a timeout or
a CI setup step that fails once is a hypothesis, not a diagnosis: many such errors persist
and point to a real cause, sometimes a subtle one.
- Before calling it transient, find what it depends on and test that directly: reproduce
  the failing operation alone (a minimal probe job, the one command, the one request) and
  compare it with a variant that should work (another resolver, image, region, version or
  input). Find the narrowest thing that differs.
- A rerun counts as evidence only if it passes. If the same error returns on a rerun, stop
  calling it transient and diagnose it. Do not schedule more reruns or tell the user to
  wait, and do not merge past it on the strength of "it's flaky".
- Report "transient" only with the evidence: a passing rerun, or a probe that shows the
  cause is outside your control. Then still offer a workaround if one exists.
Example: GitHub runners failed apt with "Temporary failure resolving 'archive.ubuntu.com'"
on every job and on every rerun. A probe job showed the runner's DNS server resolved no
*.ubuntu.com name on any image, while 1.1.1.1 did. Routing ubuntu.com lookups to public
resolvers (a systemd-resolved drop-in) fixed it. Two reruns and a 40-minute wait had
fixed nothing.
