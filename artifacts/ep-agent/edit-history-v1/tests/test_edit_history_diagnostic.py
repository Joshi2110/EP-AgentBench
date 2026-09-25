"""Focused offline tests; fake completions only, no real model generation."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('edit_history',ROOT/'diagnostics/edit_history.py')
diag=importlib.util.module_from_spec(spec);spec.loader.exec_module(diag)


class DiagnosticTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.workspace=self.root/'workspace';self.workspace.mkdir()
        self.path=self.workspace/'a.py';self.path.write_bytes(b'x = 1\ny = 2\n')
        self.observed={'path':'a.py','version':'v1','sha256':diag.sha(self.path.read_bytes())}
        self.args={'path':'a.py','version':'v1','start_line':1,'end_line':2,'new_text':'x = 1\ny = 2\n# done\n'}

    def tearDown(self):self.tmp.cleanup()

    def test_line_edit_whole_and_partial_ranges_preserve_exact_bytes(self):
        diag.line_edit(self.workspace,self.args,self.observed)
        self.assertEqual(self.path.read_bytes(),self.args['new_text'].encode())
        self.path.write_bytes(b'first\r\nsecond\r\nthird')
        self.observed['sha256']=diag.sha(self.path.read_bytes())
        a={**self.args,'start_line':2,'end_line':2,'new_text':'middle\r\n'}
        diag.line_edit(self.workspace,a,self.observed)
        self.assertEqual(self.path.read_bytes(),b'first\r\nmiddle\r\nthird')

    def test_paths_symlinks_hardlinks_and_wrong_observed_file_rejected(self):
        (self.root/'outside.py').write_text('outside')
        (self.workspace/'link.py').symlink_to(self.root/'outside.py')
        import os
        os.link(self.root/'outside.py',self.workspace/'hard.py')
        (self.workspace/'other.py').write_text('other')
        for name in ['../outside.py',str(self.root/'outside.py'),'link.py','hard.py','other.py']:
            with self.subTest(name=name),self.assertRaises(ValueError):
                diag.line_edit(self.workspace,{**self.args,'path':name},self.observed)
        self.assertEqual((self.root/'outside.py').read_text(),'outside')

    def test_stale_version_and_changed_current_bytes_rejected(self):
        with self.assertRaisesRegex(ValueError,'version'):
            diag.line_edit(self.workspace,{**self.args,'version':'v0'},self.observed)
        self.path.write_bytes(b'x = 9\ny = 2\n')
        with self.assertRaisesRegex(ValueError,'version'):
            diag.line_edit(self.workspace,self.args,self.observed)
        self.assertEqual(self.path.read_bytes(),b'x = 9\ny = 2\n')

    def test_invalid_ranges_and_utf8_size_checks_leave_source_unchanged(self):
        original=self.path.read_bytes()
        for start,end in [(0,1),(2,1),(1,3),(-1,2),(True,2),(1,2.0)]:
            with self.subTest(start=start,end=end),self.assertRaises(ValueError):
                diag.line_edit(self.workspace,{**self.args,'start_line':start,'end_line':end},self.observed)
        with self.assertRaisesRegex(ValueError,'Replacement'):
            diag.line_edit(self.workspace,{**self.args,'new_text':'é'*128001},self.observed)
        with self.assertRaisesRegex(ValueError,'Result'):
            diag.line_edit(self.workspace,{**self.args,'end_line':1,'new_text':'x'*256000},self.observed)
        self.assertEqual(self.path.read_bytes(),original)

    def test_schema_wrappers_extra_fields_and_legacy_b_call(self):
        good=json.dumps({'tool':'edit_lines','arguments':self.args})
        self.assertEqual(diag.parse_response('```json\n'+good+'\n```','B')[1],self.args)
        for obj in [ {'tool':'edit_lines','arguments':{**self.args,'extra':1}},
                     {'tool':'edit_lines','arguments':{**self.args,'start_line':True}},
                     {'tool':'edit_file','arguments':{'path':'a.py','old_text':'x','new_text':'y'}} ]:
            with self.assertRaises(ValueError):diag.parse_response(json.dumps(obj),'B')
        for text in [good+' commentary','```json\n'+good,good+'\n'+good]:
            with self.assertRaises(ValueError):diag.parse_response(text,'B')

    def test_schedule_source_history_actual_failures_and_target_not_supplied(self):
        cells=diag.cells();self.assertEqual(len(cells),8)
        self.assertEqual(len({c['id'] for c in cells}),8)
        for c in cells:
            self.assertNotIn(c['expected_source'],json.dumps(c['messages']))
            self.assertNotIn(json.dumps(c['expected_source'])[1:-1],json.dumps(c['messages']))
            self.assertEqual(c['historical_actual_result']['detail'],'old_text must match exactly once')
            self.assertEqual(c['expected_source'],c['source']+'# diagnostic note\n')
            same=[x for x in cells if x['task']==c['task']]
            self.assertTrue(all(x['source']==c['source'] and x['expected_source']==c['expected_source'] for x in same))
            opposite=next(x for x in same if x['interface']!=c['interface'] and x['history']==c['history'])
            self.assertEqual(c['messages'][1:],opposite['messages'][1:])
            if c['history']=='present':
                clean=next(x for x in same if x['interface']==c['interface'] and x['history']=='absent')
                self.assertEqual(c['messages'][:2]+c['messages'][3:],clean['messages'])

    def test_measure_noop_rejection_wrong_location_and_success(self):
        for c in diag.cells():
            path=self.workspace/c['path'];path.write_text(c['source'])
            if c['interface']=='A':
                args={'path':c['path'],'old_text':c['source'],'new_text':c['source']}
                name='edit_file'
            else:
                args={'path':c['path'],'version':'v1','start_line':1,'end_line':c['observation']['line_count'],'new_text':c['source']}
                name='edit_lines'
            noop=diag.measure(self.workspace,c,json.dumps({'tool':name,'arguments':args}))
            self.assertTrue(noop['schema_accepted']);self.assertFalse(noop['exact_target']);self.assertFalse(noop['source_changed'])
            rejected=diag.measure(self.workspace,c,json.dumps(c['historical_call']))
            self.assertFalse(rejected['exact_target']);self.assertTrue(rejected['repeated_misleading_call'])
            self.assertIn('error',rejected['tool_result'])
            args['new_text']='# diagnostic note\n'+c['source']
            wrong=diag.measure(self.workspace,c,json.dumps({'tool':name,'arguments':args}))
            self.assertTrue(wrong['source_changed']);self.assertFalse(wrong['exact_target'])
            path.write_text(c['source']);args['new_text']=c['expected_source']
            success=diag.measure(self.workspace,c,json.dumps({'tool':name,'arguments':args}))
            self.assertTrue(success['schema_accepted']);self.assertTrue(success['exact_target']);self.assertTrue(success['source_changed'])

    def test_harness_generates_once_per_cell_no_feedback_and_no_overwrite(self):
        calls=[];closed=[];frozen=diag.cells()
        class Fake:
            def __init__(self,model,config):self.metadata={'adapter':{'loaded':True,'sha256':{'weights':'test'}}}
            def start(self,control):pass
            def generate(self,messages,seconds,emit):
                calls.append(messages)
                # Deliberately rejected calls verify no recovery or retry occurs.
                return {'text':'{"tool":"missing","arguments":{}}','generation_tokens':9,'elapsed_seconds':0}
            def close(self):closed.append(True)
        manifest=self.root/'manifest.json';doc={'implementation_sha256':{},'model':{},'adapter':{'sha256':{'weights':'test'}},
            'versions':{},'generation':diag.GENERATION,'cells':frozen}
        manifest.write_text(json.dumps(doc));out=self.root/'run'
        with patch.object(diag,'local_model',return_value={}),patch.object(diag,'adapter_manifest',return_value={'sha256':{'weights':'test'}}):
            report=diag.run(manifest,self.root,self.root,out,backend_factory=Fake,check_boundary=lambda *a:{'verified':True})
            self.assertEqual(len(calls),8);self.assertEqual(len(closed),8);self.assertEqual(report['primary_successes'],0)
            self.assertEqual(calls,[c['messages'] for c in frozen])
            self.assertTrue(all(r['generation_calls']==1 for r in report['cells']))
            with self.assertRaises(FileExistsError):diag.run(manifest,self.root,self.root,out,backend_factory=Fake)
        self.assertEqual(len(calls),8)


if __name__=='__main__':unittest.main()
