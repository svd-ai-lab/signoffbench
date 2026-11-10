import ast, pathlib, sys, os, signal, subprocess, shutil, time, json
sys.path.insert(0,'/tests/work')
from runtime.subprocess_controller import SubprocessController
p=pathlib.Path('/tmp/grade-fixed.py');tree=ast.parse(p.read_text());cls=next(x for x in tree.body if isinstance(x,ast.ClassDef) and x.name=='IsolatedController');helper=next(x for x in tree.body if isinstance(x,ast.FunctionDef) and x.name=='cleanup_case_uids')
namespace=dict(Path=pathlib.Path,os=os,signal=signal,subprocess=subprocess,shutil=shutil,SubprocessController=SubprocessController,CASE_UID=100123,CASE_PUBLIC=pathlib.Path('/public/probe'))
namespace['CASE_PUBLIC'].mkdir(parents=True,exist_ok=True);pathlib.Path('/logs/verifier').mkdir(parents=True,exist_ok=True)
exec(compile(ast.Module(body=[helper,cls],type_ignores=[]),str(p),'exec'),namespace)
candidate=pathlib.Path('/tmp/candidate-probe.py');candidate.write_text('''import os,time
class Controller:
 def reset(self):
  if getattr(self,'spawned',False):return
  self.spawned=True
  pid=os.fork()
  if pid==0:
   os.setsid()
   time.sleep(120)
   os._exit(0)
 def step(self,o): return dict(pumpA_cmd=0.,pumpB_cmd=0.,pumpC_cmd=0.,valve_cmd=0.)
''')
c=namespace['IsolatedController'](candidate);c.reset()
def live():
 out=[]
 for proc in pathlib.Path('/proc').iterdir():
  if not proc.name.isdecimal():continue
  try:s=(proc/'status').read_text();uid=int(next(x for x in s.splitlines() if x.startswith('Uid:')).split()[1]);state=next(x for x in s.splitlines() if x.startswith('State:'))
  except (FileNotFoundError,StopIteration):continue
  if uid==100123 and '\tZ' not in state:out.append(int(proc.name))
 return out
before=live();assert len(before)>=2,before
start=time.monotonic();c.close();time.sleep(.1);after=live();assert not after,after
print(json.dumps({'test':'detached descendant retains inherited pipes','before_live_processes':len(before),'after_live_processes':len(after),'close_elapsed_s':time.monotonic()-start,'passed':True}))
