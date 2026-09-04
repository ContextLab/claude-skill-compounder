import json,os,re,glob,collections,random,sys
D=os.environ.get("LEVELB_DIR", "./levelb/")
ROOT=os.path.expanduser("~/.claude/history-surfer/projects")
W=re.compile(r'[A-Za-z0-9_]+')
def toks(s): return {w for w in (x.lower() for x in W.findall(s)) if len(w)>=3 and not w.isdigit()}
rows=[]
for f in glob.glob(os.path.join(ROOT,"*","prompts.jsonl")):
    slug=os.path.basename(os.path.dirname(f))
    for line in open(f,encoding="utf-8",errors="replace"):
        line=line.strip()
        if not line: continue
        try: r=json.loads(line)
        except: continue
        p=(r.get("prompt") or "").strip()
        if r.get("is_command") or not p: continue
        r["_slug"]=r.get("project_slug") or slug; r["_p"]=p; rows.append(r)
N=len(rows)
df=collections.Counter(); pf=collections.defaultdict(set)
for r in rows:
    t=toks(r["_p"])
    for w in t:
        df[w]+=1
        if not r["_slug"].startswith("-private-tmp"): pf[w].add(r["_slug"])
PFC={w:len(s) for w,s in pf.items()}
json.dump({"N":N,"df":df,"pf":PFC}, open(os.path.join(D,"df_pf.json"),"w"))
CUT=N*0.01
print("N=%d  rare cutoff df<%.0f"%(N,CUT))
print("project-freq distribution of tokens (non-tmp slugs):")
h=collections.Counter(min(PFC.get(w,0),20) for w in df)
for k in sorted(h): print("  PF=%s: %d tokens"%(k if k<20 else "20+",h[k]))
def rare(s): return {w for w in toks(s) if 2<=df.get(w,0)<CUT}
SUB=[r for r in rows if len(r["_p"].split())>=6]
# PROJ is a list of history-surfer project slugs (cwd with "/" -> "-") to measure over.
# Set LEVELB_PROJECTS to a comma-separated list of slugs from ~/.claude/history-surfer/projects.
PROJ=[p for p in os.environ.get("LEVELB_PROJECTS","").split(",") if p]
if not PROJ:
    print("set LEVELB_PROJECTS to a comma-separated list of project slugs", file=sys.stderr); sys.exit(1)
cands_all=[r for r in SUB if not r["_slug"].startswith("-private-tmp")]
random.seed(11); pool=collections.defaultdict(list); stats={}
for CUR in PROJ:
    Q=[(r.get("session_id"),r["_p"][:1200]) for r in SUB if r["_slug"]==CUR]
    C=[r for r in cands_all if r["_slug"]!=CUR]
    CT=[rare(r["_p"]) for r in C]
    for k in (3,4):
        fired=0;tot=0
        for sid,q in Q:
            qt=rare(q); sc=sorted(((len(qt&CT[i]),i) for i in range(len(C)) if len(qt&CT[i])>=k), reverse=True)
            if sc:
                fired+=1; tot+=len(sc)
                if k==4 or (k==3 and sc[0][0]==3):
                    for rank,(n,i) in enumerate(sc[:3]):
                        pool[(CUR,k)].append({"proj":CUR,"kband":k,"rank":rank,"n":n,"sid":sid,
                          "query":q,"cand":C[i]["_p"][:1200],"slug":C[i]["_slug"],
                          "shared":sorted(qt&CT[i])})
        stats[(CUR,k)]=(fired,len(Q),tot)
        print("%-42s k>=%d: fire=%d/%d (%.0f%%) hits=%d mean_per_firing=%.1f"%(
            CUR,k,fired,len(Q),100*fired/len(Q),tot,tot/max(1,fired)))
json.dump({str(k):v for k,v in stats.items()}, open(os.path.join(D,"rare2_stats.json"),"w"), indent=1)
# sample: 20 per project at k>=4, prefer rank 0
S=[]
for CUR in PROJ:
    p=pool[(CUR,4)]
    r0=[x for x in p if x["rank"]==0]; rr=[x for x in p if x["rank"]>0]
    random.shuffle(r0); random.shuffle(rr)
    S += (r0+rr)[:20]
S3=[]
for CUR in PROJ:
    p=[x for x in pool[(CUR,3)] if x["n"]==3 and x["rank"]==0]
    random.shuffle(p); S3 += p[:2]
S3=S3[:5]
for i,x in enumerate(S): x["pid"]="q%02d"%i
for i,x in enumerate(S3): x["pid"]="t%02d"%i
json.dump(S+S3, open(os.path.join(D,"rare_sample2.json"),"w"), indent=1)
print("sampled k>=4: %d (rank0=%d)  n==3: %d"%(len(S),sum(1 for x in S if x["rank"]==0),len(S3)))
print("by project:", collections.Counter(x["proj"] for x in S))
