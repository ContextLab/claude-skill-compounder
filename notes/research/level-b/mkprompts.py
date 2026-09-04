import json,os
D=os.environ.get("LEVELB_DIR", "./levelb/")
os.makedirs(os.path.join(D,"prompts"),exist_ok=True)
S=json.load(open(os.path.join(D,"sample60.json")))
T=("Two prompts a developer typed at a coding assistant, from two different projects.\n\n"
   "PROMPT A (the request being worked on now):\n<<<\n{a}\n>>>\n\n"
   "PROMPT B (an older prompt from a different project):\n<<<\n{b}\n>>>\n\n"
   "Would seeing prompt B while working on the request in prompt A help avoid repeating a "
   "mistake or forgetting a constraint? Answer RELEVANT or IRRELEVANT and one sentence.")
for p in S:
    open(os.path.join(D,"prompts",p["pid"]+".txt"),"w").write(T.format(a=p["query"][:1200], b=p["cand"][:1200]))
print("wrote", len(S))
