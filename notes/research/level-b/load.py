import json, os, re, glob, collections, sys
ROOT=os.path.expanduser("~/.claude/history-surfer/projects")
D=os.environ.get("LEVELB_DIR", "./levelb/")
rows=[]
for f in glob.glob(os.path.join(ROOT,"*","prompts.jsonl")):
    slug=os.path.basename(os.path.dirname(f))
    for line in open(f, encoding="utf-8", errors="replace"):
        line=line.strip()
        if not line: continue
        try: r=json.loads(line)
        except Exception: continue
        rows.append(r)
print("records", len(rows))
nc=[r for r in rows if not r.get("is_command") and (r.get("prompt") or "").strip()]
print("noncommand nonempty", len(nc))
# token def == toks_of in hooks/repeat-gate.sh
WORD=re.compile(r'[A-Za-z0-9_]+')
def toks(s, cap=None):
    t=set()
    for w in WORD.findall(s.lower()):
        if len(w)>=3 and not w.isdigit(): t.add(w)
    t=sorted(t)
    return set(t[:cap]) if cap else set(t)
df=collections.Counter()
for r in nc:
    for w in toks(r["prompt"]): df[w]+=1
N=len(nc)
print("distinct tokens", len(df))
for pct in (30,20,15,10,7,5,3,2,1):
    n=sum(1 for w,c in df.items() if c > N*pct/100)
    print(f"X={pct}%  stoplist size={n}")
json.dump({"N":N,"df":df}, open(os.path.join(D,"df.json"),"w"))
