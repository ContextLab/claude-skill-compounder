#!/usr/bin/env python3
"""Guard VARIANTS of four drafts, for the day a lesson can be conditioned on platform or
shell. Real CLI, sandbox3. Each pattern: should-match calls and should-not-match calls
through `compound check --guards` (the mod's invocation)."""
import json, os, subprocess
S = os.path.dirname(os.path.abspath(__file__))
CLI = "/Users/jmanning/claude-skill-compounder/bin/compound"
env = {k: v for k, v in os.environ.items() if not k.startswith("COMPOUND_") and k != "CLAUDE_CODE_SESSION_ID"}
env.update(COMPOUND_HOME=S + "/sandbox3/home", COMPOUND_CLAUDE_DIR=S + "/sandbox3/claude", COMPOUND_PROJECT=S + "/sandbox3/proj")
def run(*args, stdin=None):
    return subprocess.run([CLI, *args], input=stdin, cwd=S + "/sandbox3/proj", env=env, capture_output=True, text=True, timeout=60)
G = {
 "g-zsh-equals": ([r"(?m)(^|[;&|]\s*)echo\s+(-[neE]+\s+)?=+(\s|$|;|&)"],
   ["echo =====", "ls; echo ====== ; pwd", "make && echo ==== && make test", "echo -e ====\nls"],
   ["echo '====='", "echo \"=== done ===\"", "printf '%s\\n' '====='", "echo a=b", "FOO==bar echo hi", "grep -c '^echo ==' file", "echo --- step 2", "python3 -c 'print(1 == 2)'"]),
 "g-zsh-status-path": ([r"(?m)(^|(;|&&|\|\||[({])\s*|\b(do|then|else)\s+)((local|export|typeset|readonly|declare)\s+)?(status|path)=", r"\bfor\s+(status|path)\s+in\b", r"\bread\s+(-\w+\s+)*(status|path)\b"],
   ["status=$?", "make; status=$?; echo $status", "path=/tmp/x && ls $path", "for path in a b; do echo $path; done", "f(){ local path=$1; cat $path; }", "echo /tmp | read -r path", "if true; then status=1; fi"],
   ["git status", "exit_status=$?", "file_path=/tmp/x", "PATH=/usr/bin:$PATH ls", "curl 'https://h/x?path=1&status=2'", "./configure --path=/usr --status=ok", "rc=$?; echo $rc", "for p in a b; do echo $p; done", "python3 -c \"import os; print(os.path)\"", "kubectl get pods -o jsonpath='{.status}'"]),
 "g-macos-timeout": ([r"(?m)(^|[;&|(]\s*|\$\(\s*)timeout\s+(-\S+\s+)*\d"],
   ["timeout 60 npm test", "cd x && timeout 10s make", "out=$(timeout 5 curl -s http://h)", "timeout -k 5 30 ./run.sh", "ls |timeout 3 cat"],
   ["pytest --timeout 30", "curl --connect-timeout 5 http://h", "gtimeout 5 make", "echo 'timeout 5 is unavailable'", "npm test -- --timeout=10000", "grep -rn 'timeout 30' src/", "sleep 1 # timeout 5", "python3 -c 'requests.get(u, timeout 5)'"]),
 "g-sed-inplace-gnu": ([r"\bsed\s+(-[A-Za-hj-z]+\s+)*-i\s+(-[A-Za-z]+\s+)*['\"]?(s[/|#,@:]|\d|/|\$)"],
   ["sed -i 's/foo/bar/' f.txt", "sed -i \"s|a|b|g\" src/*.py", "find . -name '*.md' | xargs sed -i 's/x/y/'", "sed -E -i 's/a+/b/' f", "sed -i '3d' f.txt", "sed -i -e 's/a/b/' f", "sed -i '/^#/d' f"],
   ["sed -i '' 's/foo/bar/' f.txt", "sed -i.bak 's/foo/bar/' f.txt", "sed -n '1,5p' f", "sed 's/a/b/' f > g", "sed -E 's/-i s/x/' f", "gsed -i 's/a/b/' f", "perl -pi -e 's/a/b/' f", "echo 'used -i s/x/y/'", "sed -i'' -e 's/a/b/' f"]),
}
for name, (patterns, yes, no) in G.items():
    args = ["add", "--update", "--level", "user", "--name", name, "--when", "Use when testing a guard variant.", "--body", "Guard variant under test."]
    for p in patterns:
        args += ["--match", p]
    p = run(*args)
    print("\n### %s  add exit %d %s" % (name, p.returncode, (p.stderr or p.stdout).strip().splitlines()[0]))
    for pat in patterns:
        print("    match:", pat)
bad = 0
for name, (patterns, yes, no) in G.items():
    print("\n### %s" % name)
    for want, calls in ((True, yes), (False, no)):
        for command in calls:
            p = run("check", "--guards", stdin=json.dumps({"tool": "Bash", "input": {"command": command}}))
            out = json.loads(p.stdout)
            hits = [h["name"] for h in out["hits"]]
            got = name in hits
            other = [h for h in hits if h != name]
            flag = "ok  " if got == want else "BAD "
            bad += got != want
            print("  %s %-9s %-58s hits=%s%s" % (flag, "MATCH" if want else "no-match", command.replace("\n", "\\n")[:58], hits, "  (other guard hit)" if other else ""))
print("\nmismatches:", bad)
p = run("status"); print("status exit", p.returncode); print("\n".join(l for l in p.stdout.splitlines() if "PASS" in l or "FAIL" in l or "guards" in l or l.startswith("  user")))
