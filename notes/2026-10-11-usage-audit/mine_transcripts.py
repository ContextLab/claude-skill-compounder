"""First pass of the usage audit: red-to-green episodes and scratch scripts run three times, per session.
Usage: python3 mine_transcripts.py      (reads ~/.claude/projects, read-only)
MINE_EXTRA_CHECKS (environment, optional): comma-separated regular expressions for the check
scripts of the projects being read, for example `lint_docs\.sh,make_site\.sh`."""
import json,os,glob,re,collections,time
root=os.path.expanduser('~/.claude/projects'); HOME_KEY=re.sub(r'[^A-Za-z0-9]','-',os.path.expanduser('~'))+'-'; cut=time.mktime((2026,10,4,0,0,0,0,0,-1))
files=[f for f in glob.glob(root+'/*/*.jsonl') if os.path.getmtime(f)>=cut and os.path.getsize(f)>200000]
RUN=re.compile(r'(?:^|[;&|]\s*|/)(pytest|run_tests\.sh|bun test|npm test|latexmk|sphinx-build|make|ruff|claude plugin \w+' + ''.join('|' + x.strip() for x in os.environ.get('MINE_EXTRA_CHECKS', '').split(',') if x.strip()) + ')')
T=collections.Counter(); ex=[]; scratch=collections.Counter()
for f in files:
    calls={}; seq=[]
    for l in open(f,errors='ignore'):
        try:d=json.loads(l)
        except: continue
        c=(d.get('message') or {}).get('content')
        if not isinstance(c,list): continue
        for b in c:
            if not isinstance(b,dict): continue
            if b.get('type')=='tool_use': calls[b['id']]=(b['name'],b.get('input') or {})
            elif b.get('type')=='tool_result' and b.get('tool_use_id') in calls:
                n,i=calls[b['tool_use_id']]; r=b.get('content'); r=r if isinstance(r,str) else json.dumps(r)
                seq.append((n,i,bool(b.get('is_error')),r[:3000]))
    if len(seq)<10: continue
    T['sessions']+=1; proj=os.path.basename(os.path.dirname(f)).replace(HOME_KEY,'')[:24]
    T['bash calls']+=sum(n=='Bash' for n,*_ in seq); T['bash is_error']+=sum(n=='Bash' and e for n,i,e,r in seq)
    red={}; had=False
    for n,i,e,r in seq:
        if n in('Edit','Write','NotebookEdit') or (n=='Bash' and re.search(r"sed -i|<<|python3? -c|patch",i.get('command',''))):
            for v in red.values(): v[0]+=1
        if n!='Bash': continue
        c=i.get('command',''); m=RUN.search(c)
        for s in re.findall(r'(?:\$\w+|/private/tmp/\S*scratchpad)/([\w.-]+\.(?:py|sh|mjs|js))',c):
            if not e: scratch[(proj,s)]+=1
        if not m: continue
        k=m.group(1); bad=e or bool(re.search(r'\b[1-9]\d* failed|FAILED|Traceback',r))
        if bad: red.setdefault(k,[0,0]); red[k][1]+=1
        elif k in red:
            ed,fl=red.pop(k)
            if ed: T['red->green episodes (check fails, edits, same check passes)']+=1; had=True; T['  of which >=3 red runs first']+=fl>=3; ex.append((proj,k,'reds',fl,'edits',ed))
    T['sessions with a red->green episode']+=had
for k,v in T.items(): print(f'{k}: {v}')
print('hard episodes (>=3 reds):'); [print('  ',x) for x in sorted(ex,key=lambda x:-x[3])[:15]]
rr=[(k,v) for k,v in scratch.items() if v>=3]
print('scratch scripts run OK >=3 times (gone when the session ends):',len(rr)); [print('  ',k,v) for k,v in sorted(rr,key=lambda x:-x[1])[:20]]
