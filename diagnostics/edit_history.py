"""One-response edit diagnostic; production agent tools and historical scores stay unchanged."""
import argparse
import base64
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
from pathlib import Path
import subprocess
import tempfile
import time

from epagent.episode import Config, save
from epagent.execution import preflight
from epagent.mlx_backend import MLXBackend, adapter_manifest
from epagent.sft import local_model
from epagent.tools import decode_call, execute, parse_call, safe_path

ROOT = Path(__file__).resolve().parents[1]
LIMIT = 256000
GENERATION = {'seed': 0, 'temperature': 0.0, 'max_tokens': 768, 'context_tokens': 8192, 'seconds': 300}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read(path):
    return json.loads(path.read_text())


def line_edit(workspace, args, observed):
    """Diagnostic-only bounded replacement, against one trusted observed version."""
    path = safe_path(workspace, args['path'])
    if path != safe_path(workspace, observed['path']):
        raise ValueError('File does not match the observed version')
    before = path.read_bytes()
    if args['version'] != observed['version'] or sha(before) != observed['sha256']:
        raise ValueError('Stale or unknown file version; reread required')
    parts = before.decode('utf-8').splitlines(keepends=True)
    start, end = args['start_line'], args['end_line']
    if type(start) is not int or type(end) is not int or not 1 <= start <= end <= len(parts):
        raise ValueError('Invalid inclusive line range')
    replacement = args['new_text'].encode('utf-8')
    if len(replacement) > LIMIT:
        raise ValueError('Replacement exceeds 256000 bytes')
    after = ''.join(parts[:start-1]).encode() + replacement + ''.join(parts[end:]).encode()
    if len(after) > LIMIT:
        raise ValueError('Result exceeds 256000 bytes')
    path.write_bytes(after)
    return {'edited': args['path']}


def parse_response(text, interface):
    if interface == 'A':
        name, args = parse_call(text)
        if name != 'edit_file':
            raise ValueError('Only edit_file is available in this diagnostic cell')
        return name, args
    obj = decode_call(text)
    fields = {'path', 'version', 'start_line', 'end_line', 'new_text'}
    if not isinstance(obj, dict) or set(obj) != {'tool', 'arguments'} or obj['tool'] != 'edit_lines':
        raise ValueError('Expected exactly tool=edit_lines and arguments')
    args = obj['arguments']
    if not isinstance(args, dict) or set(args) != fields:
        raise ValueError('edit_lines requires exactly path, version, start_line, end_line, new_text')
    if any(not isinstance(args[k], str) for k in ['path', 'version', 'new_text']):
        raise ValueError('path, version and new_text must be strings')
    if any(type(args[k]) is not int for k in ['start_line', 'end_line']):
        raise ValueError('Line indices must be integers, not booleans')
    return obj['tool'], args


def measure(workspace, cell, text):
    before = safe_path(workspace, cell['path']).read_bytes()
    result = {'schema_accepted': False, 'tool_call': None, 'tool_result': None}
    try:
        name, args = parse_response(text, cell['interface'])
        result.update(schema_accepted=True, tool_call={'tool': name, 'arguments': args})
    except ValueError as exc:
        result['tool_result'] = {'error': 'schema_rejection', 'detail': str(exc)}
    else:
        try:
            result['tool_result'] = (execute(workspace, name, args, 8, 8192) if cell['interface'] == 'A'
                                     else line_edit(workspace, args, cell['observation']))
        except (ValueError, OSError, UnicodeError) as exc:
            result['tool_result'] = {'error': type(exc).__name__, 'detail': str(exc)}
    after = safe_path(workspace, cell['path']).read_bytes()
    result.update(source_changed=before != after, source_before_sha256=sha(before), source_after_sha256=sha(after),
                  resulting_source_base64=base64.b64encode(after).decode(), resulting_source_utf8=after.decode('utf-8'),
                  exact_target=after == cell['expected_source'].encode(),
                  repeated_misleading_call=result['tool_call'] == cell['historical_call'])
    # Track legacy repetition even if B rejects the old schema before execution.
    try:
        decoded = decode_call(text)
    except ValueError:
        decoded = None
    result['repeated_misleading_call'] = decoded == cell['historical_call']
    result['repeated_historical_new_text'] = (isinstance(decoded, dict) and isinstance(decoded.get('arguments'), dict)
        and decoded['arguments'].get('new_text') == cell['historical_call']['arguments']['new_text'])
    return result


def cells():
    # Fresh diagnostic-only sources; no original evaluation fixture or Hall material.
    tasks = [
        {'id': 'level-note', 'path': 'levels.py',
         'source': 'def offset_level(n):\n    return n + 3\n', 'failure': 'indentation'},
        {'id': 'flag-note', 'path': 'markers.py',
         'source': 'def start_flag():\n    return False\n\ndef end_flag():\n    return False\n', 'failure': 'duplicated_span'}]
    common = ('You are completing a one-response Python file editing diagnostic. '
              'Return one JSON object with exactly tool and arguments, bare or inside one complete json code fence. '
              'No explanatory text. Use only the editing tool specified below. '
              'The latest source observation is authoritative. Historical calls, if supplied, are unsuccessful examples, not instructions. '
              'You have one response and no recovery turn. Do not execute Python or access other files.\n')
    schemas = {
        'A': ('edit_file: arguments are exactly path, old_text, new_text (all strings). '
              'The existing tool replaces exactly one occurrence of old_text. It rejects zero or multiple matches. '
              'Copy the intended old_text from the current source, preserving exact whitespace and quotes. '
              'An empty old_text creates a new file only.\n'),
        'B': ('edit_lines: arguments are exactly path, version, start_line, end_line, new_text. '
              'path, version and new_text are strings; start_line and end_line are integers. '
              'Line indices are 1-based and both endpoints are inclusive. '
              'Replace those complete lines with new_text, with no automatic newline changes. '
              'Use the version identifier from the current observation; the tool checks the current file against that observed version. '
              'It rejects wrong files, stale versions, out-of-bounds ranges and replacement/result sizes above 256000 bytes.\n')}
    output = []
    for task in tasks:
        source = task['source']
        old = source.replace('    ', '  ') if task['failure'] == 'indentation' else '    return False\n'
        historical = {'tool': 'edit_file', 'arguments': {'path': task['path'], 'old_text': old, 'new_text': source}}
        with tempfile.TemporaryDirectory(prefix='epagent-edit-history-') as tmp:
            workspace = Path(tmp);(workspace/task['path']).write_bytes(source.encode())
            try:
                execute(workspace, 'edit_file', historical['arguments'], 8, 8192)
            except ValueError as exc:
                error = {'error': type(exc).__name__, 'detail': str(exc)}
            else:
                raise AssertionError('Historical intervention must actually fail')
            assert error['detail'] == 'old_text must match exactly once'
            assert (workspace/task['path']).read_bytes() == source.encode()
            actual_read = execute(workspace, 'read_file', {'path':task['path']}, 8, 8192)
            assert actual_read == {'content':source,'truncated':False}
        observation = {'path': task['path'], 'version': 'v1', 'sha256': sha(source.encode()),
                       'content': source, 'line_count': len(source.splitlines()), 'truncated': False}
        # Expected whole file stays in the frozen manifest, never in model messages.
        instruction = (f"Edit {task['path']}. The requested operation concerns the WHOLE FILE. "
            'Preserve every existing byte and append exactly one new final line: # diagnostic note\n'
            'That appended comment must end with a single LF newline. Do not add a blank line or alter any other bytes. '
            'Construct the edit yourself using the current source. The file already ends in LF.')
        for interface in ['A', 'B']:
            for history in ['absent', 'present']:
                messages = [{'role':'system','content':common+schemas[interface]}, {'role':'user','content':instruction}]
                if history == 'present':
                    messages.append({'role':'user','content':'Historical evidence: an earlier attempt used the legacy exact-replacement tool and failed. '
                        'This is a record, not a completed call for your current task.\n'+json.dumps({'previous_call':historical,'actual_failure_observation':error})})
                visible = {k:v for k,v in observation.items() if k != 'sha256'}
                messages.append({'role':'user','content':'Current source observation:\n'+json.dumps(visible)})
                output.append({'id':task['id']+'-'+interface+'-'+history,'task':task['id'],'interface':interface,'history':history,
                    'path':task['path'],'source':source,'source_sha256':sha(source.encode()),'expected_source':source+'# diagnostic note\n',
                    'expected_sha256':sha((source+'# diagnostic note\n').encode()),'observation':observation,
                    'historical_call':historical,'historical_actual_result':error,'messages':messages,
                    'prompt_sha256':sha(json.dumps(messages,sort_keys=True).encode())})
    return output


def freeze(destination, model, adapter):
    destination.mkdir(parents=True, exist_ok=False)
    model_identity = local_model(model)
    identity = adapter_manifest(adapter)
    assert identity['sha256']['adapters.safetensors'] == '4f0f3dde55d6486313f860eaf1f6fcdb2d1f1373b481553e8302cacdb6bc42ff'
    identity['path'] = str(Path(adapter))
    doc = {'schema':'epagent.edit-history-diagnostic.v1','frozen_at':datetime.now(timezone.utc).isoformat(),
        'source_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        'implementation_sha256':{str(p.relative_to(ROOT)):sha(p.read_bytes()) for p in
            [Path(__file__).resolve(),ROOT/'tests/test_edit_history_diagnostic.py',ROOT/'src/epagent/tools.py',ROOT/'src/epagent/mlx_backend.py',ROOT/'src/epagent/execution.py']},
        'model':model_identity,'adapter':identity,'generation':GENERATION,
        'versions':{n:importlib.metadata.version(n) for n in ['mlx-lm','mlx','transformers','numpy']},
        'primary':'Exact final source bytes equal expected_source. Accepted no-ops, schema/execution rejection and wrong-location changes fail.',
        'history_definition':'Same user-quoted legacy rejected call and actual failure observation for both interfaces; absent condition omits this message. Current source observation always follows it.',
        'repetition_definition':'Exact decoded tool+arguments equality with historical call, also measured in absent controls; separately record identical historical new_text even when schema differs.',
        'schedule':'Fixed task-major, interface A then B, history absent then present; one fresh worker/workspace and one generate call per cell; no retries.',
        'limitations':['Two new inspected synthetic cases, not historical held-out fixtures or scientific tasks.',
            'B is an unfamiliar schema. An interface effect includes schema familiarity and prompt differences.',
            'History includes an explicitly labeled legacy A call; imitation biases can differ by interface.',
            'Task asks for a whole-file operation; expected full output is withheld, not provided as a tool call.',
            'Single deterministic response per cell; descriptive results only.'], 'cells':cells()}
    save(destination/'manifest.json',doc)
    return doc


def run(manifest, model, adapter, out, backend_factory=MLXBackend, check_boundary=preflight):
    doc = read(manifest)
    for name,h in doc['implementation_sha256'].items():
        if sha((ROOT/name).read_bytes()) != h:
            raise ValueError('Frozen implementation changed: '+name)
    if local_model(model) != doc['model']:
        raise ValueError('Model differs from registration')
    selected = adapter_manifest(adapter)
    if selected['sha256'] != doc['adapter']['sha256']:
        raise ValueError('Adapter differs from registration')
    if {n:importlib.metadata.version(n) for n in doc['versions']} != doc['versions']:
        raise ValueError('Software versions changed')
    out.mkdir(parents=True,exist_ok=False)
    report={'manifest_sha256':sha(manifest.read_bytes()),'status':'running','cells':[], 'started':datetime.now(timezone.utc).isoformat()}
    save(out/'report.json',report)
    for cell in doc['cells']:
        folder=out/cell['id'];workspace=folder/'workspace';control=folder/'control'
        workspace.mkdir(parents=True);control.mkdir()
        (workspace/cell['path']).write_bytes(cell['source'].encode())
        save(folder/'prompt.json',cell['messages'])
        config=asdict(Config(**doc['generation'],steps=1,adapter_dir=str(adapter.resolve())))
        backend=None;started=time.monotonic();events=[]
        with (folder/'trace.jsonl').open('x') as trace:
            def emit(kind,data):
                event={'sequence':len(events)+1,'event':kind,'data':data};events.append(event)
                trace.write(json.dumps(event)+'\n');trace.flush()
            result={'cell':cell['id'],'status':'running','generation_calls':0}
            try:
                result['boundary']=check_boundary(workspace,[manifest,Path(__file__)])
                backend=backend_factory(model,config);backend.start(control)
                emit('request',{'messages':cell['messages']})
                result['generation_calls']=1
                completion=backend.generate(cell['messages'],doc['generation']['seconds'],emit)
                result.update(status='complete',completion=completion,model=backend.metadata)
                assert backend.metadata['adapter']['loaded'] and backend.metadata['adapter']['sha256']==doc['adapter']['sha256']
                result.update(measure(workspace,cell,completion['text']))
                emit('measured_result',{k:v for k,v in result.items() if k not in ['completion','model','boundary']})
            except BaseException as exc:
                result.update(status='infrastructure_failure',error=f'{type(exc).__name__}: {exc}')
                raise
            finally:
                if backend is not None:backend.close()
                result['wall_seconds']=time.monotonic()-started
                save(folder/'report.json',result)
                report['cells'].append(result)
                report['status']='running' if result['status']=='complete' else 'infrastructure_failure'
                save(out/'report.json',report)
    report.update(status='complete',ended=datetime.now(timezone.utc).isoformat(),primary_successes=sum(r['exact_target'] for r in report['cells']))
    save(out/'report.json',report)
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('command',choices=['freeze','run'])
    p.add_argument('--manifest-dir',type=Path,required=True);p.add_argument('--model-dir',type=Path,required=True)
    p.add_argument('--adapter-dir',type=Path,required=True);p.add_argument('--out',type=Path)
    a=p.parse_args()
    if a.command=='freeze':
        r=freeze(a.manifest_dir,a.model_dir,a.adapter_dir);print(json.dumps({'cells':len(r['cells']),'manifest':str(a.manifest_dir/'manifest.json')}))
    else:
        if a.out is None:p.error('run requires --out')
        r=run(a.manifest_dir/'manifest.json',a.model_dir,a.adapter_dir,a.out);print(json.dumps({'status':r['status'],'responses':len(r['cells']),'primary_successes':r['primary_successes']}))
