# Provenance for served artifacts: processes, ports, containers, remotes

Load this when the thing you are exercising reaches you over a socket rather than through
an import. The canary rule from `SKILL.md` is unchanged: plant a unique token on the path
the request must traverse, then find it in the response. What changes is where the old copy
hides.

## A previous session's process still owns the port

This is routine, not exotic. Server processes spawned by an editor or agent session are
frequently reparented to PID 1 when the session ends and keep running indefinitely. A new
`npm run dev` then finds the port busy, silently picks a fallback port, and you spend the
next half hour reloading a page served by yesterday's build.

```bash
lsof -ti:3000                       # PID(s) holding the port
ps -o pid=,lstart=,command= -p PID  # started when, by what command
lsof -p PID | grep -w cwd           # which directory it is serving from
```

Three questions, in order:

1. Is that PID's `cwd` this project? If not, you are testing an unrelated app.
2. Is its start time older than your edit? Then it cannot contain the edit.
3. Did your dev server actually bind the port you are loading? Read its startup output
   again rather than assuming the default port.

Kill by the specific PID you identified. Never blanket-kill by process name: matching on
`node` or `python` reliably takes down unrelated work, including other agents' servers.

## The browser or CDN is showing you a cached response

Check the artifact, not the rendering. `curl` bypasses every layer of browser cache:

```bash
curl -sS -D- -o /dev/null http://localhost:3000/            # status and headers
curl -sS http://localhost:3000/ | grep -c 'CANARY-7f3a'     # canary in the served HTML
curl -sS http://localhost:3000/assets/index.js | head -c 200
```

If `curl` shows the canary and the browser does not, the server is current and the problem
is client-side: hard reload, disable cache in devtools, or check a service worker
(`navigator.serviceWorker.getRegistrations()`), which will happily serve an old bundle
offline-first forever.

If `curl` does not show the canary, the server is stale. Go back to the build check in
`SKILL.md`, then to the process check above.

## Containers

The image predates the edit, or the build used a cached layer, or a bind mount is shadowing
the baked-in copy with something else.

```bash
docker images --format '{{.Repository}}:{{.Tag}}  {{.CreatedAt}}'   # image older than the edit?
docker ps --format '{{.ID}}  {{.Image}}  {{.CreatedAt}}  {{.Command}}'
docker exec CONTAINER grep -r 'CANARY-7f3a' /app | head            # canary inside the container
docker inspect CONTAINER --format '{{json .Mounts}}'               # what is mounted over what
```

`docker exec ... grep` for the canary is the direct proof and it outranks every timestamp.
If the canary is missing inside the container, rebuild without the layer cache
(`docker build --no-cache`) rather than guessing which `COPY` line went stale, and confirm
the container was recreated afterwards: `docker compose up` reuses an existing container
even when the image changed unless it is told otherwise.

A bind mount is the inverted case. The image is fine and the mount is serving an old host
directory, so check `.Mounts` before rebuilding anything.

## Remote and deployed copies

```bash
ssh HOST 'grep -c CANARY-7f3a /srv/app/current/main.js'
ssh HOST 'ls -l --time-style=full-iso /srv/app/current'   # symlink target and its age
git rev-parse HEAD                                        # local commit
ssh HOST 'cat /srv/app/current/REVISION'                  # deployed commit, if recorded
```

Comparing the deployed revision against local `HEAD` is faster than any timestamp
comparison, and it is the check worth adding to the deploy pipeline permanently. When
nothing records a revision, the canary is the fallback.

Two recurring traps: a release directory that was uploaded but never symlinked as
`current`, and a load balancer with more than one backend, where refreshing lands you on
an updated node roughly half the time. Intermittent correctness after a deploy is a routing
symptom, not a code symptom. Pin to one backend before drawing any conclusion.

## Serverless and edge

A new version is published but traffic is still routed to the previous alias, or a warm
execution environment is holding module-level state from the old code. Invoke the specific
published version by qualifier rather than the alias, and check the version identifier that
the platform reports in its own logs against the one you just published.
