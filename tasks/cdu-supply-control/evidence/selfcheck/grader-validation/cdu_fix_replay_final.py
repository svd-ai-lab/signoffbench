import pathlib,subprocess,concurrent.futures,json,time,hashlib
r=pathlib.Path('/opt/sb/codex167-official-campaign-20261106');out=r/'review-fix-validation-final';out.mkdir(exist_ok=True)
def run(name):
 src=next((r/('preflight' if name=='oracle01' else 'jobs-retry01')/name).glob('task__*'))
 candidate=src/'artifacts/app/submission/controller.py'
 if not candidate.exists():raise RuntimeError('No frozen candidate: '+str(candidate))
 dest=out/name;dest.mkdir(exist_ok=True)
 cmd=['docker','run','--rm','--network','none','--cpus','4','--memory','8g','--entrypoint','python','-v',str(r/'grade.py')+':/tests/grade.py:ro','-v',str(candidate.parent)+':/app/submission:ro','-v',str(dest)+':/logs/verifier','sha256:767f4c598160d2fea2487d439b66859a59bc155fa5323b6b9c8fb8b6fbccf77c','/tests/grade.py']
 start=time.time()
 with (out/(name+'.log')).open('w') as f:p=subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT,timeout=920)
 old=json.load(open(src/'verifier/report.json'));new=json.load(open(dest/'report.json'))
 differences=[case for case,c in old['cases'].items() if any(c.get(k)!=new['cases'].get(case,{}).get(k) for k in ['metrics','selected_acceptance','passed'])]
 return {'run':name,'command':cmd,'exit_code':p.returncode,'elapsed_s':time.time()-start,'old_reward':old['reward'],'new_reward':new['reward'],'candidate_sha256':new['candidate_sha256'],'differences':differences,'case_count':len(new['cases'])}
# normal05 was copied from res-2 with its original raw job, not regenerated.
names=['oracle01','normal01','normal02','normal03','normal04','normal05']
rows=[]
with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
 for f in concurrent.futures.as_completed([pool.submit(run,n) for n in names]):
  try:rows.append(f.result())
  except Exception as e:rows.append({'error':str(e)})
  (out/'receipt.json').write_text(json.dumps({'grader_sha256':hashlib.sha256((r/'grade.py').read_bytes()).hexdigest(),'runs':rows},indent=2))
