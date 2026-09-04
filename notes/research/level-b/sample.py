import json,os,random,collections
D=os.environ.get("LEVELB_DIR", "./levelb/")
random.seed(43)
# tag must match what rank3.py wrote (CUR.replace("/","_") + "_notmp_all"/"_notmp_first")
TAG=os.environ.get("LEVELB_TAG", "")
if not TAG:
    print("set LEVELB_TAG to the project tag rank3.py wrote pairs_<TAG>_notmp_{all,first}.json for")
pairs=json.load(open(os.path.join(D,f"pairs_{TAG}_notmp_all.json")))
pairs+=json.load(open(os.path.join(D,f"pairs_{TAG}_notmp_first.json")))
# dedupe on (query, candidate); keep the token-criterion record (jaccard dupes carry same text)
seen={}
for p in pairs:
    key=(p["query"][:200], p["cand"][:200])
    if key not in seen or p["crit"]=="tokens": seen[key]=p
uniq=list(seen.values())
def bucket(n):
    if n<3: return "n2"
    if n==3: return "n3"
    if n==4: return "n4"
    if n==5: return "n5"
    if n<=9: return "n6_9"
    return "n10+"
by=collections.defaultdict(list)
for p in uniq: by[bucket(p["n_shared"])].append(p)
print({k:len(v) for k,v in by.items()}, "unique pairs", len(uniq))
sample=[]
for b in ("n2","n3","n4","n5","n6_9","n10+"):
    v=by[b]; random.shuffle(v)
    sample+= v[:10]
for i,p in enumerate(sample): p["pid"]=f"p{i:02d}"; p["bucket"]=bucket(p["n_shared"])
json.dump(sample, open(os.path.join(D,"sample60.json"),"w"), indent=1)
print("sample", len(sample), collections.Counter(p["bucket"] for p in sample))
print("jaccard range in sample:", min(p["jaccard"] for p in sample), max(p["jaccard"] for p in sample))
