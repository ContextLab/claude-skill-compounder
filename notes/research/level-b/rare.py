import json,os,re,glob,collections,sys
D=os.environ.get("LEVELB_DIR", "./levelb/")
ROOT=os.path.expanduser("~/.claude/history-surfer/projects")
WORD=re.compile(r'[A-Za-z0-9_]+')
dfd=json.load(open(os.path.join(D,"df.json"))); N=dfd["N"]; df=dfd["df"]
RARE_MAX=N*0.01   # token appears in <1% of prompts
def toks(s): return {w for w in (x.lower() for x in WORD.findall(s)) if len(w)>=3 and not w.isdigit()}
def rare(s): return {w for w in toks(s) if df.get(w,0) < RARE_MAX and df.get(w,0)>=2}
rows=[]
for f in glob.glob(os.path.join(ROOT,"*","prompts.jsonl")):
    slug=os.path.basename(os.path.dirname(f))
    for line in open(f,encoding="utf-8",errors="replace"):
        line=line.strip()
        if not line: continue
        try: r=json.loads(line)
        except: continue
        p=(r.get("prompt") or "").strip()
        if r.get("is_command") or not p or len(p.split())<6: continue
        r["_slug"]=r.get("project_slug") or slug; r["_p"]=p; rows.append(r)
# CUR is a history-surfer project slug (cwd with "/" -> "-"), e.g. the slug for the repo
# this note was measured on. Set it via env or edit before running.
CUR=os.environ.get("LEVELB_CUR", "")
if not CUR:
    print("set LEVELB_CUR to a project slug from ~/.claude/history-surfer/projects", file=sys.stderr); sys.exit(1)
sess=collections.defaultdict(list)
for r in rows:
    if r["_slug"]==CUR: sess[r.get("session_id")].append(r)
Q=[]
for sid,rs in sess.items():
    rs.sort(key=lambda r:(r.get("seq") or 0))
    for r in rs: Q.append((sid,r["_p"][:1200]))
cands=[r for r in rows if r["_slug"]!=CUR and not r["_slug"].startswith("-private-tmp")]
ct=[rare(c["_p"]) for c in cands]
print("queries",len(Q),"cands",len(cands),"rare-token vocab cutoff df<%d"%RARE_MAX)
out=[]
for k in (2,3,4):
    fired=0;tot=0;top=[]
    for sid,q in Q:
        qt=rare(q); sc=[]
        for i,c in enumerate(ct):
            n=len(qt&c)
            if n>=k: sc.append((n,i))
        if sc:
            fired+=1;tot+=len(sc);sc.sort(reverse=True)
            for n,i in sc[:3]: top.append({"k":k,"n":n,"query":q,"cand":cands[i]["_p"][:1200],"slug":cands[i]["_slug"],"shared":sorted(qt&ct[i])[:20]})
    print(f"rare k>={k}: fire={fired}/{len(Q)} ({fired/len(Q):.0%}) hits={tot} mean={tot/len(Q):.1f}")
    if k==3: out=top
json.dump(out, open(os.path.join(D,"rare_top.json"),"w"), indent=1)
seen=set(); shown=0
for t in out:
    key=t["query"][:80]
    if key in seen: continue
    seen.add(key); shown+=1
    print("--- n=%d %s  shared: %s"%(t["n"],t["slug"]," ".join(t["shared"][:12])))
    if shown>=12: break
