"""Describe the frozen eight responses and verify preservation; no inference or repair."""
from pathlib import Path
from datetime import datetime,timezone
import base64,hashlib,json
root=Path(__file__).resolve().parents[2];control=Path(__file__).resolve().parent
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
manifest=root/'data/epagent-edit-history-v1/manifest.json';doc=read(manifest);report=read(root/'attempts/edit-history-v1/report.json')
assert sha(manifest)==read(control/'registration.json')['manifest_sha256']==report['manifest_sha256']
assert report['status']=='complete' and len(report['cells'])==8
for name,h in doc['implementation_sha256'].items():assert sha(root/name)==h
protected=read(control/'protected-before.json');assert all(sha(Path(n))==h for n,h in protected.items())
rows=[];responses=0
for cell,r in zip(doc['cells'],report['cells']):
 assert r['cell']==cell['id'] and r['generation_calls']==1 and r['status']=='complete'
 folder=root/'attempts/edit-history-v1'/cell['id'];trace=[json.loads(s) for s in (folder/'trace.jsonl').read_text().splitlines()]
 assert sum(e['event']=='request' for e in trace)==sum(e['event']=='model_done' for e in trace)==1
 ready=next(e['data']['metadata'] for e in trace if e['event']=='model_ready')
 assert ready['adapter']['loaded'] and ready['adapter']['sha256']==doc['adapter']['sha256']
 assert ready['model_id']==doc['model']['model_id'] and ready['revision']==doc['model']['revision']
 assert ready['stop_token_ids']==[151643,151645]
 assert read(folder/'prompt.json')==cell['messages']
 final=(folder/'workspace'/cell['path']).read_bytes();assert final==base64.b64decode(r['resulting_source_base64'])
 expected=cell['expected_source'].encode();assert r['exact_target']==(final==expected)
 text=r['completion']['text'];responses+=1
 try:parsed=json.loads(text);valid_json=True
 except ValueError:parsed=None;valid_json=False
 repeated_old=(isinstance(parsed,dict) and isinstance(parsed.get('arguments'),dict)
               and parsed['arguments'].get('old_text')==cell['historical_call']['arguments']['old_text'])
 if not r['schema_accepted']:
  reason='Invalid JSON and invented replace tool' if not valid_json else 'Invented replace tool / invalid arguments layout' if cell['interface']=='A' else 'Positional arguments array instead of required object'
 elif 'error' in r['tool_result']:
  reason='Ambiguous old_text occurs twice; execution rejected'
 elif final+b'\n'==expected:
  reason='Correct source retained and comment appended, but required final LF missing'
 elif final==b'# diagnostic note\n':
  reason='Whole source replaced with comment only; original source deleted'
 else:reason='Other target-byte mismatch'
 rows.append({'cell':cell['id'],'task':cell['task'],'interface':cell['interface'],'history':cell['history'],
              'valid_json':valid_json,'schema_accepted':r['schema_accepted'],'execution_accepted':r['schema_accepted'] and 'error' not in r['tool_result'],
              'source_changed':r['source_changed'],'exact_target':r['exact_target'],'repeated_entire_historical_call':r['repeated_misleading_call'],
              'repeated_historical_old_text':repeated_old,'reason':reason,'wall_seconds':r['wall_seconds'],
              'generation_seconds':r['completion']['elapsed_seconds'],'generated_tokens':r['completion']['generation_tokens'],
              'termination':r['completion']['finish_reason'],'generated_response':text,'actual_tool_result':r['tool_result'],
              'resulting_source_base64':r['resulting_source_base64'],'resulting_source_utf8':r['resulting_source_utf8'],
              'expected_sha256':cell['expected_sha256'],'final_sha256':r['source_after_sha256'],
              'report':str(folder.relative_to(root)/'report.json'),'trace':str(folder.relative_to(root)/'trace.jsonl'),'workspace':str(folder.relative_to(root)/'workspace')})
assert responses==8
result={'schema':'epagent.edit-history-result.v1','analysis_time':datetime.now(timezone.utc).isoformat(),'registration_sha256':sha(manifest),
 'primary':{'successes':sum(r['exact_target'] for r in rows),'responses':responses},'cells':rows,
 'schema_by_history':{h:sum(r['schema_accepted'] for r in rows if r['history']==h) for h in ['absent','present']},
 'successes_by_interface':{i:sum(r['exact_target'] for r in rows if r['interface']==i) for i in ['A','B']},
 'total_generated_tokens':sum(r['generated_tokens'] for r in rows),'execution':read(control/'execution.json'),
 'cleanup':read(control/'cleanup.json'),'protected_files_unchanged':len(protected),
 'versions':doc['versions'],'model':doc['model'],'adapter':doc['adapter'],
 'interpretation':'No exact targets. Present-history calls all pass schema; absent-history calls all fail schema. History supplies an object-shaped legacy call as well as misleading edit contents, so format demonstration and misleading content are bundled. Exact copying succeeds in one A/present cell, but LF is missing. B/present constructs valid version/ranges but deletes source. No full-call repetition; A/present repeated-span case reuses the ambiguous old_text with altered new_text.',
 'limitations':['Two inspected tasks; one deterministic response per cell; no statistical or scientific-generalization claim.',
 'The compact system prompt names arguments fields but does not explicitly say that arguments must be an object. Strict validators require it. History supplies such an example; schema failures limit interface-friction conclusions.',
 'History is labeled user-quoted legacy evidence, not an assistant-history replay of SFT v3. Lack of repetition here does not negate earlier observations.',
 'B has an unfamiliar schema; representation, prompt and familiarity effects are inseparable in this small interface contrast.',
 'No hidden-output hints were supplied: full expected files stayed in the frozen registration, outside prompts. The harmless comment itself is prescribed by the task.',
 'Trusted local harness with existing preflight and path confinement; no new production security claim.']}
(control/'result.json').write_text(json.dumps(result,indent=2)+'\n')
lines=['# Eight-response edit-interface/history diagnostic','', '**Primary: 0/8 exact targets.** Exactly eight real-model responses, no recovery turn or replacement attempt.','',
 '| Task | Interface | History | Schema | Executed | Changed | Target | Tokens | Wall seconds |',
 '| --- | --- | --- | --- | --- | --- | --- | ---: | ---: |']
for r in rows:
 yn=lambda v:'yes' if v else 'no'
 lines.append(f"| {r['task']} | {r['interface']} | {r['history']} | {yn(r['schema_accepted'])} | {yn(r['execution_accepted'])} | {yn(r['source_changed'])} | {yn(r['exact_target'])} | {r['generated_tokens']} | {r['wall_seconds']:.3f} |")
lines+=['','Executed means tool execution accepted, not just schema acceptance. Wall seconds include preflight, loading, generation, editing and worker cleanup.','',result['interpretation'],'','## Individual responses and actual results','']
for r in rows:
 lines += ['### '+r['cell'],'',r['reason']+'.','', '```json', r['generated_response'],'```','',
           'Tool result: `'+json.dumps(r['actual_tool_result'])+'`','',
           'Exact final source (JSON string makes trailing newlines explicit):','', '```json',json.dumps(r['resulting_source_utf8']),'```','']
lines+=['## Interpretation limits','',*['- '+s for s in result['limitations']],'',
 'All eight workers loaded the frozen v3 adapter with the recorded configuration/weight hashes; stop IDs were [151643, 151645]. All ended generation with stop, well below the 768-token budget. Total generated tokens: '+str(result['total_generated_tokens'])+'.',
 '', 'Executed collection command (once, with attached caffeinate):','', '```bash',
 'PYTHONPATH=src .venv/bin/python diagnostics/edit_history.py run --manifest-dir data/epagent-edit-history-v1 --model-dir .epagent-models/qwen2.5-coder-1.5b-4bit --adapter-dir sft-runs/tool-use-lora-v3 --out attempts/edit-history-v1','```','',
 f"Registration SHA-256: `{sha(manifest)}`. Eight focused offline tests passed before generation. All {len(protected)} protected pre-existing files remain unchanged. All experiment-owned processes exited. No weights, historical datasets, physics tools or scorers were changed, and no frozen experiment was rescored."]
(control/'report.md').write_text('\n'.join(lines)+'\n')
files={}
for folder in [root/'attempts/edit-history-v1',control,root/'data/epagent-edit-history-v1']:
 for p in folder.rglob('*'):
  if p.is_file() and p.name!='artifact-sha256.json':files[str(p.relative_to(root))]={'sha256':sha(p),'bytes':p.stat().st_size}
for p in [root/'diagnostics/edit_history.py',root/'tests/test_edit_history_diagnostic.py']:
 files[str(p.relative_to(root))]={'sha256':sha(p),'bytes':p.stat().st_size}
(control/'artifact-sha256.json').write_text(json.dumps({'schema':'epagent.artifact-inventory.v1','files':files,'excludes':'this inventory itself'},indent=2)+'\n')
print(json.dumps({'responses':responses,'primary':result['primary'],'schema_by_history':result['schema_by_history'],'tokens':result['total_generated_tokens'],'protected_files_unchanged':len(protected),'artifacts':len(files)},indent=2))
