class Controller:
 def reset(self): pass
 def step(self,o): return dict(pumpA_cmd=float('nan'),pumpB_cmd=0.,pumpC_cmd=0.,valve_cmd=0.)
