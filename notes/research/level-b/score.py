import json,os,re,collections
D=os.environ.get("LEVELB_DIR", "./levelb/")
S=json.load(open(os.path.join(D,"sample60.json")))
def verdict(t):
    t=t.strip().upper()
    if t.startswith("IRRELEVANT") or re.search(r'\bIRRELEVANT\b',t[:200]): return "I"
    if re.search(r'\bRELEVANT\b',t[:200]): return "R"
    return "?"
rec=[]
for p in S:
    v=[]
    for r in (1,2):
        f=os.path.join(D,"judgements","%s.r%d.txt"%(p["pid"],r))
        v.append(verdict(open(f).read()) if os.path.exists(f) else "?")
    rel = (v[0]=="R" and v[1]=="R")
    rec.append({**{k:p[k] for k in ("pid","bucket","n_shared","jaccard","cand_slug")}, "v":v, "rel":rel})
json.dump(rec, open(os.path.join(D,"verdicts.json"),"w"), indent=1)
agree=sum(1 for r in rec if r["v"][0]==r["v"][1]); print("run-to-run agreement: %d/60"%agree)
print("unparsed:", sum(1 for r in rec if "?" in r["v"]))
print()
print("| bucket | n | relevant | precision |")
by=collections.defaultdict(list)
for r in rec: by[r["bucket"]].append(r)
order=["n2","n3","n4","n5","n6_9","n10+"]
for b in order:
    v=by[b]; k=sum(1 for x in v if x["rel"])
    print(f"| {b} | {len(v)} | {k} | {k/len(v):.2f} |")
print()
# precision at threshold k over the sample, weighted by the POPULATION frequency of buckets
# TAG must match the project tag used for sample.py / rank3.py's output.
TAG=os.environ.get("LEVELB_TAG", "")
pairs=json.load(open(os.path.join(D,f"pairs_{TAG}_notmp_all.json")))
pairs+=json.load(open(os.path.join(D,f"pairs_{TAG}_notmp_first.json")))
seen={}
for p in pairs:
    key=(p["query"][:200], p["cand"][:200])
    if key not in seen or p["crit"]=="tokens": seen[key]=p
uniq=list(seen.values())
def bk(n):
    return "n2" if n<3 else "n3" if n==3 else "n4" if n==4 else "n5" if n==5 else "n6_9" if n<=9 else "n10+"
pop=collections.Counter(bk(p["n_shared"]) for p in uniq)
prec={b:(sum(1 for x in by[b] if x["rel"])/len(by[b])) for b in order}
print("population of surfaced (top-3) pairs by bucket:", dict(pop))
print()
print("| threshold | surfaced pairs (pop) | weighted precision | FPR = 1-prec | judged n |")
for k,bs in ((2,order),(3,order[1:]),(4,order[2:]),(5,order[3:])):
    tot=sum(pop[b] for b in bs)
    if tot==0: continue
    wp=sum(pop[b]*prec[b] for b in bs)/tot
    jn=sum(len(by[b]) for b in bs)
    print(f"| k>={k} | {tot} | {wp:.2f} | {1-wp:.2f} | {jn} |")
# jaccard-based
print()
print("| jaccard cutoff | judged n | relevant | precision | FPR |")
for jc in (0.05,0.08,0.10,0.15,0.20):
    v=[r for r in rec if r["jaccard"]>=jc]
    if not v: continue
    k=sum(1 for x in v if x["rel"])
    print(f"| >={jc} | {len(v)} | {k} | {k/len(v):.2f} | {1-k/len(v):.2f} |")
