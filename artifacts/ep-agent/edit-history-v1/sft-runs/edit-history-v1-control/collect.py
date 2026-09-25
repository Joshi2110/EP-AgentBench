"""Launch exactly one frozen diagnostic collection with caffeinate and durable logs."""
from pathlib import Path
import hashlib,json,os,subprocess,time
from datetime import datetime,timezone
root=Path(__file__).resolve().parents[2];out=Path(__file__).resolve().parent
record=out/'execution.json';assert not record.exists()
registration=json.loads((out/'registration.json').read_text())
assert hashlib.sha256((root/'data/epagent-edit-history-v1/manifest.json').read_bytes()).hexdigest()==registration['manifest_sha256']
command=['.venv/bin/python','diagnostics/edit_history.py','run','--manifest-dir','data/epagent-edit-history-v1','--model-dir','.epagent-models/qwen2.5-coder-1.5b-4bit','--adapter-dir','sft-runs/tool-use-lora-v3','--out','attempts/edit-history-v1']
env=dict(os.environ);env['PYTHONPATH']='src'
now=lambda:datetime.now(timezone.utc).isoformat()
r={'command':command,'environment_overrides':{'PYTHONPATH':'src'},'start':now(),'status':'starting','wrapper_pid':os.getpid()}
record.write_text(json.dumps(r,indent=2)+'\n');started=time.monotonic();child=awake=None
try:
 with (out/'stdout.log').open('xb') as stdout,(out/'stderr.log').open('xb') as stderr:
  child=subprocess.Popen(command,cwd=root,env=env,stdout=stdout,stderr=stderr)
  awake=subprocess.Popen(['/usr/bin/caffeinate','-i','-s','-w',str(child.pid)])
  r.update(pid=child.pid,caffeinate_pid=awake.pid,status='running');record.write_text(json.dumps(r,indent=2)+'\n')
  code=child.wait();r.update(exit_code=code,status='complete' if code==0 else 'failed')
except BaseException as exc:
 r.update(status='wrapper_failure',error=f'{type(exc).__name__}: {exc}')
 if child is not None and child.poll() is None:
  child.terminate()
  try:child.wait(timeout=10)
  except subprocess.TimeoutExpired:child.kill();child.wait()
 raise
finally:
 if awake is not None:
  try:awake.wait(timeout=5)
  except subprocess.TimeoutExpired:awake.terminate();awake.wait(timeout=5)
 r.update(end=now(),wall_seconds=time.monotonic()-started,child_reaped=child is None or child.poll() is not None,caffeinate_reaped=awake is None or awake.poll() is not None)
 record.write_text(json.dumps(r,indent=2)+'\n')
print(json.dumps(r,indent=2));raise SystemExit(r.get('exit_code',1))
