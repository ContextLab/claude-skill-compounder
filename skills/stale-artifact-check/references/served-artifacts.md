# Provenance for served artifacts: processes, ports, containers, remotes

Load this when the thing you are exercising reaches you over a socket rather than through
an import. The rule from `SKILL.md` is unchanged: put `$CANARY` on the path the request must
traverse, then find it on the other side. What changes is where the old copy hides.

**Which canary form works here.** A `raise` on a request path does not print your token to
the client, it produces a 500 and puts the token in the server log. That is still an
observation, and a strong one. If you want the token in the response body itself, use the
printed-marker form (a response header, a comment in the rendered HTML, a field in the JSON)
and grep for it there. Match the form to where you intend to look.

## A previous session's process still owns the port

Routine, not exotic. Server processes spawned by an editor or agent session are frequently
reparented to PID 1 when the session ends and keep running. A new `npm run dev` then finds
the port busy, silently picks a fallback, and the page you keep reloading is yesterday's
build on the original port.

```bash
lsof -ti:3000                       # PID(s) holding the port
ps -o pid=,lstart=,command= -p PID  # started when, by what command
lsof -p PID | grep -w cwd           # which directory it is serving from
```

Three questions, in order:

1. Is that PID's `cwd` this project? If not, you are testing an unrelated app.
2. Is its start time older than your edit? Then it cannot contain the edit.
3. Did your dev server actually bind the port you are loading? Read its startup output
   again rather than assuming the default.

Kill the specific PID you identified. Never blanket-kill by process name: matching `node` or
`python` reliably takes down unrelated work, including other agents' servers.

## The browser or a CDN is showing you a cached response

Check the artifact, not the rendering. `curl` bypasses every layer of browser cache.

```bash
curl -sS -D- -o /dev/null http://localhost:3000/          # status and headers
curl -sS http://localhost:3000/ | grep -c "$CANARY"       # printed-marker canary in the HTML
curl -sS -o /dev/null -w '%{http_code}\n' http://localhost:3000/   # 500 means a raise canary fired
```

If `curl` sees the canary and the browser does not, the server is current and the problem is
client-side: hard reload, disable cache in devtools, or check for a service worker
(`navigator.serviceWorker.getRegistrations()`), which serves an old bundle offline-first
indefinitely. If `curl` does not see it, the server is stale: go back to the build check in
`SKILL.md`, then to the process check above.

## Containers

The image predates the edit, a cached layer was reused, or a bind mount is shadowing the
baked-in copy.

```bash
docker images --format '{{.Repository}}:{{.Tag}}  {{.CreatedAt}}'
docker ps --format '{{.ID}}  {{.Image}}  {{.CreatedAt}}  {{.Command}}'
docker exec CONTAINER grep -r "$CANARY" /app | head     # the direct proof
docker inspect CONTAINER --format '{{json .Mounts}}'    # what is mounted over what
```

The `exec` grep outranks every timestamp. If the canary is missing inside the container,
rebuild with `--no-cache` rather than guessing which `COPY` went stale, then confirm the
container was actually recreated: `docker compose up` reuses an existing container even when
the image changed unless told otherwise. A bind mount is the inverted case, where the image
is fine and the mount serves an old host directory, so read `.Mounts` before rebuilding.

## Remote and deployed copies

```bash
ssh HOST 'grep -c "'"$CANARY"'" /srv/app/current/main.js'
ssh HOST 'ls -ld /srv/app/current && ls -l /srv/app/releases | tail -3'
git rev-parse HEAD                        # local commit
ssh HOST 'cat /srv/app/current/REVISION'  # deployed commit, if anything records one
```

Comparing the deployed revision against local `HEAD` beats any timestamp comparison, and it
is the check worth adding to the deploy pipeline permanently. Keep the `ls` plain: GNU-only
flags such as `--time-style=full-iso` fail on a BSD or macOS remote, and `ls -l` plus
`ls -ld` on the symlink answers the same question everywhere.

Two recurring traps: a release directory uploaded but never symlinked as `current`, and a
load balancer with more than one backend, where refreshing lands on an updated node roughly
half the time. Intermittent correctness after a deploy is a routing symptom, not a code
symptom, so pin to one backend before concluding anything.

## Serverless and edge

A new version is published but traffic still routes to the previous alias, or a warm
execution environment holds module-level state from the old code. Invoke the specific
published version by qualifier rather than the alias, and compare the version identifier the
platform reports in its own logs against the one you just published.

## Test runner caches

A green suite is the most expensive place to be wrong.

- The test imported the installed copy rather than the tree. Run the import check from
  `SKILL.md` inside the test process, not from the shell, since the runner changes
  `sys.path`.
- `.pytest_cache`, `.tox`, `node_modules/.cache`, `.next/cache`, and Jest's transform cache
  can all serve earlier output. Delete the directory rather than reasoning about it.
- A collection error in one file can leave the runner reporting the rest of the suite as
  passing. Compare the test count against the previous run before believing an improvement.
