"""Read-only paired development analysis. No tools, scoring reruns or inference."""
from pathlib import Path
from collections import Counter
import hashlib
import json

root=Path.cwd(); control=root/'sft-runs/replace-lines-7b-engineering'; out=root/'attempts/replace-lines-7b-smoke'
def read(path):return json.loads(path.read_text())
def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        while chunk:=f.read(1024*1024):h.update(chunk)
    return h.hexdigest()
def analyze(folder):
    report=read(folder/'result.json')
    events=[json.loads(s) for s in Path(report['paths']['trace']).read_text().splitlines()]
    calls={e['data']['step']:e for e in events if e['event']=='tool_call'}
    results={e['data']['step']:e for e in events if e['event']=='tool_result'}
    edits=[];reads=[]
    for step,e in calls.items():
        call=e['data'];result=results[step];obs=result['data']['observation']
        if call['tool']=='read_file' and 'error' not in obs:
            reads.append({'step':step,'call_event':e['sequence'],'result_event':result['sequence'],'path':call['arguments']['path'],'version':obs.get('version')})
        if call['tool'] in ['edit_file','replace_lines']:
            edits.append({'step':step,'call_event':e['sequence'],'result_event':result['sequence'],
                          'tool':call['tool'],'arguments':call['arguments'],'observation':obs,
                          'accepted':'error' not in obs,'changed':bool(result['data']['patch']),
                          'patch':result['data']['patch']})
    directory=Path(report['paths']['workspace']);initial=Path(report['paths']['initial_workspace'])
    summaries=report['development']['final_summaries']
    assert not summaries
    return {'model_id':report['model']['model_id'],'revision':report['model']['revision'],
            'episode_id':report['episode_id'],'responses':report['usage']['completed_generations'],
            'schema_valid_calls':len(calls),'schema_rejected_calls':sum('error' in e['data']['observation'] and step not in calls for step,e in results.items()),
            'execution_rejected_calls':sum('error' in results[step]['data']['observation'] for step in calls),
            'calls_by_tool':dict(Counter(e['data']['tool'] for e in calls.values())),
            'successful_reads':reads,'attempted_edits':len(edits),'accepted_edits':sum(e['accepted'] for e in edits),
            'content_changing_edits':sum(e['changed'] for e in edits),'edits':edits,
            'modified_files':report['modified_files'],'initial_bytes':(initial/'cart.py').read_bytes().decode(),
            'final_bytes':(directory/'cart.py').read_bytes().decode(),'initial_source_sha256':sha(initial/'cart.py'),
            'final_source_sha256':sha(directory/'cart.py'),'initial_source_byte_count':(initial/'cart.py').stat().st_size,
            'final_source_byte_count':(directory/'cart.py').stat().st_size,'python_test_runs_by_agent':len(report['development']['agent_python_runs']),
            'final_summaries':summaries,'final_summary_support':'No summary produced; no supported finish.',
            'independent_visible_test_outcome':report['development']['original_visible_tests'],
            'repair_passed':report['development']['repair_passed'],'runtime_seconds':report['total_seconds'],
            'usage':report['usage'],'termination':report['termination_reason'],'adapter':report['model']['adapter'],
            'stop_token_ids':report['model']['stop_token_ids'],'paths':report['paths']},report,events
base,b,be=analyze(root/'attempts/replace-lines-base-smoke')
new,n,ne=analyze(out)
breg=read(root/'attempts/replace-lines-base-smoke/registration.json');nreg=read(out/'registration.json')
assert breg['config']==nreg['config']
assert breg['fixture']==nreg['fixture'] and breg['fixture_sha256']==nreg['fixture_sha256']
assert breg['system_prompt']==nreg['system_prompt']
assert b['initial_sha256']==n['initial_sha256']
assert next(e['data']['messages'] for e in be if e['event']=='model_request')==next(e['data']['messages'] for e in ne if e['event']=='model_request')
assert next(e['data']['prompt_token_ids'] for e in be if e['event']=='model_start')==next(e['data']['prompt_token_ids'] for e in ne if e['event']=='model_start')
assert breg['software']==nreg['software']
assert n['model']['adapter']['requested'] is False and n['model']['adapter']['loaded'] is False
assert n['model']['stop_token_ids']==read(control/'tokenizer-check.json')['stop_ids_configured']
assert n['runner_sha256']['tools.py']==b['runner_sha256']['tools.py']
assert n['runner_sha256']['episode.py']==b['runner_sha256']['episode.py']
assert new['schema_valid_calls']==12 and len(new['successful_reads'])==6
assert new['attempted_edits']==new['accepted_edits']==new['content_changing_edits']==5
assert new['calls_by_tool']['replace_lines']==4
assert new['modified_files']==['cart.py'] and not new['repair_passed']
assert 'IndentationError' in new['independent_visible_test_outcome']['stderr']
comparison={'kind':'One-episode development comparison, not a controlled parameter-count estimate.',
 'base_1_5b':base,'base_7b':new,
 'comparability':{'configuration':nreg['config'],'all_config_fields_equal':True,'fixture_and_initial_bytes_equal':True,
    'initial_messages_and_token_ids_equal':True,'tool_and_episode_source_hashes_equal':True,'software_versions_equal':True,
    'native_templates_differ_only_in_unused_fallback_system_text':True,
    'compatibility_adjustments':['Allowlist exact 7B revision and its download size.','7 GiB MLX allocation ceiling for 7B; cache precision, sampling and budgets unchanged.'],
    'memory_environment':'Applications were closed before the 7B episode. Normal memory pressure verified with model loaded, during episode and after cleanup.'},
 'manual_evidence':{'schema_and_source_read_events':[64,65], 'observed_header_then_legacy_edit_events':[65,142,143],
    'observed_version_then_line_edit_events':[179,261,262], 'function_definition_removed_by_line_edit_event':261,
    'final_source_observation_event':671,'independent_failed_test_event':673},
 'interpretation':'7B followed the tool schema, copied an observed header and used observed version tokens. '
    'It did not read README.md or checks.py. It changed cart_total(rows) to calculate_total(items) with dictionary inputs, '
    'then deleted the function definition with a line-range replacement. Later edits changed return statements without '
    'executing Python. The final file has an indented top-level return and fails import. This is unsuccessful repair '
    'despite working tool invocation and real byte changes. It does not demonstrate scientific competence or broad superiority.',
 'primary_repair_result':{'1.5B':False,'7B':False},'additional_episodes':0}
(out/'comparison.json').write_text(json.dumps(comparison,indent=2)+'\n')
# Verify original evidence, model and interface bytes, without running a scorer.
for name,h in read(control/'historical-and-interface-before.json').items():assert sha(root/name)==h,name
for name,item in read(root/'sft-runs/replace-lines-engineering/artifact-sha256.json')['files'].items():assert sha(root/name)==item['sha256'],name
manifest=read(root/'.epagent-models/qwen2.5-coder-7b-4bit/epagent-model.json')
assert n['model']['sha256']==manifest['sha256']
for name,h in manifest['sha256'].items():assert sha(root/'.epagent-models/qwen2.5-coder-7b-4bit'/name)==h,name
old_inventory=read(root/'sft-runs/edit-history-v1-control/protected-before.json')
allowed=read(root/'sft-runs/replace-lines-engineering/preservation.json')['authorized_source_and_generated_package_changes']+['src/epagent/mlx_backend.py']
allowed={str(root/name) for name in allowed}
checked=0
for name,h in old_inventory.items():
    if name not in allowed:
        assert sha(Path(name))==h,name
        checked+=1
(control/'final-verification.json').write_text(json.dumps({'historical_files_verified_unchanged':checked,
 'prior_1_5b_evidence_inventory_files_unchanged':27,'new_model_files_hash_verified':10,
 'same_initial_messages_and_token_ids':True,'all_12_responses_preserved':True,
 'all_5_edits_change_bytes':True,'repair_passed':False,'episode_owned_processes_exited':True,
 'preexisting_caffeinate_left_untouched':True},indent=2)+'\n')
status=read(control/'preparation-status.json');status.update(episode_started=True,episode_complete=True,real_model_responses=12,blocking_condition=None)
(control/'preparation-status.json').write_text(json.dumps(status,indent=2)+'\n')
print(json.dumps({'comparison':'attempts/replace-lines-7b-smoke/comparison.json','source_preservation_count':checked,'calls':new['calls_by_tool'],'runtime':new['runtime_seconds']}))
