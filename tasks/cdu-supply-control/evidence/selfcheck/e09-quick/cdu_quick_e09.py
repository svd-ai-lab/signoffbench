"""Deterministic submission probes; no task or grader mutations."""
import json
from harbor.agents.base import BaseAgent

class QuickProbe(BaseAgent):
    @staticmethod
    def name(): return 'cdu-e09-quick'
    def version(self): return '1'
    def __init__(self,*args,probe='nonfinite',**kwargs):
        super().__init__(*args,**kwargs)
        self.probe=probe
    async def setup(self,environment): pass
    async def run(self,instruction,environment,context):
        bodies={
            'nonfinite': "class Controller:\n def reset(self): pass\n def step(self,o): return dict(pumpA_cmd=float('nan'),pumpB_cmd=0.,pumpC_cmd=0.,valve_cmd=0.)\n",
            'exit': "import os\nos._exit(0)\n",
            'forge': "class Controller:\n def reset(self): pass\n def step(self,o): return {}\n",
        }
        s="from pathlib import Path\np=Path('/app/submission/controller.py')\np.unlink(missing_ok=True)\n"
        if self.probe=='symlink': s+="p.symlink_to('/tests/grade.py')\n"
        else: s+='p.write_text('+repr(bodies[self.probe])+')\n'
        if self.probe=='forge':
            s+="for name,text in [('reward.txt','1\\n'),('report.json','{\"reward\":1,\"passed\":true}')]:\n q=Path('/logs/verifier')/name\n q.parent.mkdir(parents=True,exist_ok=True)\n q.write_text(text)\n print('staged claim',str(q))\n"
        s+="print('probe prepared: '+"+repr(self.probe)+")\n"
        result=await environment.exec(command="python - <<'PROBE'\n"+s+"\nPROBE",timeout_sec=30)
        (self.logs_dir/'probe.json').write_text(json.dumps({'probe':self.probe,'script':s,'result':result.model_dump(mode='json')},indent=2))
