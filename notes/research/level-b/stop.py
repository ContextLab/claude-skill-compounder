import json,os,collections
D=os.environ.get("LEVELB_DIR", "./levelb/")
d=json.load(open(os.path.join(D,"df.json"))); N=d["N"]; df=d["df"]
for pct,name in ((5,"stoplist_5pct.txt"),(3,"stoplist_3pct.txt"),(10,"stoplist_10pct.txt")):
    lst=sorted([w for w,c in df.items() if c > N*pct/100], key=lambda w:-df[w])
    open(os.path.join(D,name),"w").write("\n".join(lst)+"\n")
    if pct==5:
        print("X=5%% size=%d"%len(lst))
        print("top40:", " ".join(lst[:40]))
        print("tail30:", " ".join(lst[-30:]))
