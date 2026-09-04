import json,os,re,glob,collections,sys
D=os.environ.get("LEVELB_DIR", "./levelb/")
ROOT=os.path.expanduser("~/.claude/history-surfer/projects")
WORD=re.compile(r'[A-Za-z0-9_]+')
STOP=set(open(os.path.join(D,"stoplist_5pct.txt")).read().split())
def toks(s):
    return {w for w in (x.lower() for x in WORD.findall(s)) if len(w)>=3 and not w.isdigit()} - STOP
rows=[]
for f in glob.glob(os.path.join(ROOT,"*","prompts.jsonl")):
    slug=os.path.basename(os.path.dirname(f))
    for line in open(f,encoding="utf-8",errors="replace"):
        line=line.strip()
        if not line: continue
        try: r=json.loads(line)
        except Exception: continue
        p=(r.get("prompt") or "").strip()
        if r.get("is_command") or not p: continue
        r["_slug"]=r.get("project_slug") or slug
        r["_p"]=p
        rows.append(r)

CUR=sys.argv[1]
EXCL_TMP = len(sys.argv)>2 and sys.argv[2]=="notmp"

# queries: first substantive (>=6 words) prompt per session in CUR, truncated 1200
sess=collections.defaultdict(list)
for r in rows:
    if r["_slug"]==CUR: sess[r.get("session_id")].append(r)
queries=[]
MODE=os.environ.get("QMODE","first")
for sid,rs in sess.items():
    rs.sort(key=lambda r:(r.get("seq") or 0))
    for r in rs:
        if len(r["_p"].split())>=6:
            queries.append((sid, r["_p"][:1200]))
            if MODE=="first": break
# candidates: substantive prompts from OTHER projects
cands=[]
for r in rows:
    s=r["_slug"]
    if s==CUR: continue
    if EXCL_TMP and s.startswith("-private-tmp"): continue
    if len(r["_p"].split())<6: continue
    cands.append((s, r.get("session_id"), r.get("ts"), r["_p"]))
ctoks=[toks(c[3]) for c in cands]
print(f"# CUR={CUR} excl_tmp={EXCL_TMP}")
print(f"queries={len(queries)} candidates={len(cands)}")

CAP=3
res={}
pairs=[]
for k in (2,3,4,5,6,8,10,12):
    fired=0; tot=0
    for qi,(sid,q) in enumerate(queries):
        qt=toks(q)
        sc=[]
        for i,ct in enumerate(ctoks):
            n=len(qt&ct)
            if n>=k: sc.append((n,len(qt&ct)/max(1,len(qt|ct)),i))
        if sc:
            fired+=1; tot+=len(sc)
            sc.sort(key=lambda x:(-x[0],-x[1]))
            for n,j,i in sc[:CAP]:
                pairs.append({"k":k,"crit":"tokens","sid":sid,"query":q,"n_shared":n,"jaccard":round(j,4),
                              "cand_slug":cands[i][0],"cand_ts":cands[i][2],"cand":cands[i][3][:1200],
                              "shared":sorted(qt&ctoks[i])[:25]})
    res[k]=(fired,tot)
    print(f"k={k}: queries_with_hit={fired}/{len(queries)} ({fired/max(1,len(queries)):.0%})  total_hits={tot}  hits/query(mean)={tot/max(1,len(queries)):.1f}")
for jc in (0.10,0.15,0.20,0.25):
    fired=0; tot=0
    for qi,(sid,q) in enumerate(queries):
        qt=toks(q); sc=[]
        for i,ct in enumerate(ctoks):
            u=len(qt|ct)
            if u==0: continue
            j=len(qt&ct)/u
            if j>=jc and len(qt&ct)>=2: sc.append((j,len(qt&ct),i))
        if sc:
            fired+=1; tot+=len(sc)
            sc.sort(key=lambda x:(-x[0],-x[1]))
            for j,n,i in sc[:CAP]:
                pairs.append({"k":f"J{jc}","crit":"jaccard","sid":sid,"query":q,"n_shared":n,"jaccard":round(j,4),
                              "cand_slug":cands[i][0],"cand_ts":cands[i][2],"cand":cands[i][3][:1200],
                              "shared":sorted(toks(q)&ctoks[i])[:25]})
    print(f"jaccard>={jc}: queries_with_hit={fired}/{len(queries)} ({fired/max(1,len(queries)):.0%})  total_hits={tot}")
tag=CUR.replace("/","_")+("_notmp" if EXCL_TMP else "_all")+"_"+MODE
json.dump(pairs, open(os.path.join(D,"pairs_"+tag+".json"),"w"), indent=0)
print("wrote", os.path.join(D,"pairs_"+tag+".json"), len(pairs), "capped pairs")
