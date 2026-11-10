import ast,pathlib,subprocess,os,signal,json,time,uuid
p=pathlib.Path('/tmp/grade-fixed.py');tree=ast.parse(p.read_text());nodes=[x for x in tree.body if isinstance(x,ast.FunctionDef) and x.name in ['cleanup_case_uids','supervise']]
ns=dict(Path=pathlib.Path,subprocess=subprocess,os=os,signal=signal,json=json,time=time,uuid=uuid,assessment_cases=lambda:[])
exec(compile(ast.Module(body=nodes,type_ignores=[]),str(p),'exec'),ns)
out=pathlib.Path('/tmp/timeout-output');out.mkdir()
worker=pathlib.Path('/tmp/timeout-worker.py');worker.write_text('''import os,json,subprocess,time,pathlib
out=pathlib.Path('/tmp/timeout-output')
uid=100456
(out/'candidate-process-uids.json').write_text(json.dumps({'verifier_run_id':os.environ['DC05_VERIFIER_RUN_ID'],'uids':[uid]}))
def drop():os.setgroups([]);os.setgid(uid);os.setuid(uid)
p=subprocess.Popen(['python','-c','import time;time.sleep(120)'],preexec_fn=drop,start_new_session=True)
(out/'pid').write_text(str(p.pid))
time.sleep(120)
''')
ns['supervise'](['python',str(worker)],out,timeout_s=2)
pid=int((out/'pid').read_text());time.sleep(.1);status=pathlib.Path('/proc')/str(pid)/'status';alive=status.exists() and '\nState:\tZ' not in '\n'+status.read_text()
assert not alive;report=json.load(open(out/'report.json'));assert report['reward']==0 and report['error']['type']=='TimeoutError'
print(json.dumps({'test':'supervisor timeout cleans separate-session candidate','passed':True,'candidate_alive_after_timeout':alive,'reward':report['reward']}))
