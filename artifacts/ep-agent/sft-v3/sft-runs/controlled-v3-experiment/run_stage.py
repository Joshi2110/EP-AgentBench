"""Execution/evidence wrapper only; invokes the frozen CLI without changing configuration."""
import json,os,subprocess,sys,time
from datetime import datetime,timezone
from pathlib import Path
root=Path(__file__).resolve().parents[2]
out=Path(__file__).resolve().parent
stage=sys.argv[1]
common=['--fixtures','data/epagent-sft-v3/eval-fixtures.json','--protocol','data/epagent-sft-v3/eval-protocol.json','--model-dir','.epagent-models/qwen2.5-coder-1.5b-4bit']
commands={
 'base':['.venv/bin/epagent','synthetic','--arm','base',*common,'--out','attempts/tool-recovery-v3-base'],
 'train':['.venv/bin/python','-m','epagent.sft','train','--prepared','sft-runs/reviewed-prepared-v3','--model-dir','.epagent-models/qwen2.5-coder-1.5b-4bit','--out','sft-runs/tool-use-lora-v3'],
 'adapted':['.venv/bin/epagent','synthetic','--arm','adapted',*common,'--adapter-dir','sft-runs/tool-use-lora-v3','--out','attempts/tool-recovery-v3-adapted']}
command=commands[stage]
record=out/(stage+'-execution.json')
if record.exists():raise SystemExit('Stage already launched; no automatic retry')
if stage!='base':
 base=json.loads((root/'attempts/tool-recovery-v3-base/suite.json').read_text())
 assert len(base['cases'])==4 and base['status']=='complete'
 for c in base['cases']:
  r=json.loads(Path(c['report']).read_text())
  assert all(Path(r['paths'][p]).is_file() for p in ['report','trace','conversation','patch'])
if stage=='adapted':
 training=json.loads((root/'sft-runs/tool-use-lora-v3/run.json').read_text())
 assert training['status']=='complete' and training['updates_requested']==138
now=lambda:datetime.now(timezone.utc).isoformat()
env=dict(os.environ);env.pop('PYTHONPATH',None)
if stage=='train':env['PYTHONPATH']='src'
info={'stage':stage,'command':command,'cwd':str(root),'environment_overrides':{'PYTHONPATH':env.get('PYTHONPATH')},'started':now(),'wrapper_pid':os.getpid(),'status':'starting'}
record.write_text(json.dumps(info,indent=2)+'\n')
started=time.monotonic();child=awake=None
try:
 with (out/(stage+'.stdout.log')).open('xb') as stdout,(out/(stage+'.stderr.log')).open('xb') as stderr:
  child=subprocess.Popen(command,cwd=root,env=env,stdout=stdout,stderr=stderr)
  awake=subprocess.Popen(['/usr/bin/caffeinate','-i','-s','-w',str(child.pid)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
  info.update(pid=child.pid,caffeinate_pid=awake.pid,caffeinate_command=['/usr/bin/caffeinate','-i','-s','-w',str(child.pid)],status='running')
  record.write_text(json.dumps(info,indent=2)+'\n')
  code=child.wait();info.update(exit_code=code,status='complete' if code==0 else 'failed')
except BaseException as exc:
 info.update(status='wrapper_failure',error=f'{type(exc).__name__}: {exc}')
 if child is not None and child.poll() is None:
  child.terminate()
  try:child.wait(timeout=15)
  except subprocess.TimeoutExpired:child.kill();child.wait()
 raise
finally:
 if awake is not None:
  try:awake.wait(timeout=5)
  except subprocess.TimeoutExpired:awake.terminate();awake.wait(timeout=5)
 info.update(ended=now(),wall_seconds=time.monotonic()-started,child_reaped=child is None or child.poll() is not None,caffeinate_reaped=awake is None or awake.poll() is not None)
 record.write_text(json.dumps(info,indent=2)+'\n')
print(json.dumps(info,indent=2))
raise SystemExit(info.get('exit_code',1))
