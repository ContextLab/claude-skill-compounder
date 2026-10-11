#!/usr/bin/env python3
"""Build the corpus for the guard study: every Bash call with its result, from every
transcript under ~/.claude/projects (subagent transcripts included). Read-only on
~/.claude. Writes one pickle to the path given as argv[1] (a scratch directory: the
corpus holds private command text and is not kept in the repository).

A call is keyed on its tool_use id, so a call copied into a resumed session's transcript
is counted once."""
import glob, json, os, pickle, sys

ROOT = os.path.expanduser("~/.claude/projects")
RESULT_HEAD, RESULT_TAIL = 6000, 3000


def text_of(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(b.get("text", "") if isinstance(b, dict) else str(b) for b in content)
    return json.dumps(content)


def main(out):
    files = sorted(glob.glob(ROOT + "/**/*.jsonl", recursive=True))
    calls, results, bad_lines = {}, {}, 0
    for path in files:
        project = os.path.relpath(path, ROOT).split(os.sep)[0]
        try:
            handle = open(path, errors="replace")
        except OSError:
            continue
        for line in handle:
            if '"tool_use"' not in line and '"tool_result"' not in line:
                continue
            try:
                d = json.loads(line)
            except ValueError:
                bad_lines += 1
                continue
            content = (d.get("message") or {}).get("content")
            if not isinstance(content, list):
                continue
            for b in content:
                if not isinstance(b, dict):
                    continue
                if b.get("type") == "tool_use" and b.get("name") == "Bash":
                    cmd = (b.get("input") or {}).get("command")
                    if isinstance(cmd, str) and b.get("id") not in calls:
                        calls[b["id"]] = {"id": b["id"], "command": cmd, "ts": d.get("timestamp", ""),
                                          "project": project, "file": path,
                                          "session": d.get("sessionId", ""),
                                          "sidechain": bool(d.get("isSidechain")),
                                          "cwd": d.get("cwd", "")}
                elif b.get("type") == "tool_result" and b.get("tool_use_id") not in results:
                    t = text_of(b.get("content"))
                    if len(t) > RESULT_HEAD + RESULT_TAIL:
                        t = t[:RESULT_HEAD] + "\n...[cut]...\n" + t[-RESULT_TAIL:]
                    results[b["tool_use_id"]] = (bool(b.get("is_error")), t)
    rows = []
    for key, call in calls.items():
        if key in results:
            call["is_error"], call["result"] = results[key]
            rows.append(call)
    rows.sort(key=lambda r: r["ts"])
    with open(out, "wb") as handle:
        pickle.dump(rows, handle)
    print("files", len(files), "bash calls", len(calls), "with result", len(rows),
          "is_error", sum(r["is_error"] for r in rows), "unparsed lines", bad_lines)
    print("first", rows[0]["ts"], "last", rows[-1]["ts"])


if __name__ == "__main__":
    main(sys.argv[1])
