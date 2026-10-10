import json
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import urllib.request
import urllib.error
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'Vydra_Docker_HF'))
from local_gui import RunManager, make_server

class LocalGuiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.source = self.root / 'input.faa'
        self.source.write_text('>protein\nMKKL\n')
        self.worker = self.root / 'worker.py'
        self.worker.write_text("import json,sys,time\nfrom pathlib import Path\np=Path(sys.argv[1]);s=json.loads(p.read_text());print('worker started',flush=True);time.sleep(.2);s.update(status='completed',stage='Completed');p.write_text(json.dumps(s))\n")
        self.manager = RunManager(self.root / 'state', self.worker)
    def tearDown(self):
        self.manager.close()
        self.tmp.cleanup()
    def values(self):
        return dict(mode='file',input=str(self.source),output=str(self.root/'output'))
    def wait_done(self):
        deadline=time.time()+5
        while time.time()<deadline:
            if not self.manager.processes:return
            time.sleep(.03)
        self.fail('Worker did not finish')
    def test_completion_and_history(self):
        state=self.manager.start(self.values());self.wait_done()
        self.assertEqual(self.manager.runs()[0]['status'],'completed')
        self.assertIn('worker started',(self.manager.directory/(state['id']+'.log')).read_text())
        self.assertEqual(RunManager(self.manager.directory).runs()[0]['id'],state['id'])
    def test_validation_and_cancellation(self):
        output=self.root/'output';output.mkdir();(output/'existing').write_text('keep')
        with self.assertRaises(ValueError):self.manager.start(self.values())
        self.worker.write_text('import time\ntime.sleep(30)\n')
        values=self.values();values['output']=str(self.root/'new')
        state=self.manager.start(values)
        with self.assertRaises(ValueError):self.manager.start(values)
        self.manager.cancel(state['id']);self.wait_done()
        self.assertEqual(self.manager.runs()[0]['status'],'cancelled')
        self.assertEqual((output/'existing').read_text(),'keep')
    def test_completed_report_and_assets_are_confined_to_results(self):
        output=self.root/'results';report=output/'informe_inferencia';report.mkdir(parents=True)
        (report/'informe.html').write_text('<h1>Results</h1>')
        (report/'data.json').write_text('{"count":2}')
        (self.root/'private.txt').write_text('private')
        (report/'escape.txt').symlink_to(self.root/'private.txt')
        state=dict(id='saved',status='complete',created_at='2026-10-10',output=str(output),report_path=str(report/'informe.html'))
        (self.manager.directory/'saved.json').write_text(json.dumps(state))
        server=make_server(self.manager);threading.Thread(target=server.serve_forever,daemon=True).start()
        base=f'http://127.0.0.1:{server.server_port}'
        try:
            self.assertIn(b'Results',urllib.request.urlopen(base+'/reports/saved/').read())
            self.assertEqual(json.load(urllib.request.urlopen(base+'/reports/saved/data.json')),{'count':2})
            for path in ['escape.txt','%2e%2e/%2e%2e/private.txt']:
                with self.assertRaises(urllib.error.HTTPError) as error:urllib.request.urlopen(base+'/reports/saved/'+path)
                self.assertEqual(error.exception.code,403)
            with self.assertRaises(urllib.error.HTTPError) as error:urllib.request.urlopen(base+'/reports/unknown/')
            self.assertEqual(error.exception.code,404)
        finally:server.shutdown();server.server_close()

    def test_local_api_requires_token_and_origin(self):
        server=make_server(self.manager);threading.Thread(target=server.serve_forever,daemon=True).start()
        base=f'http://127.0.0.1:{server.server_port}'
        try:
            config=json.load(urllib.request.urlopen(base+'/api/config'))
            request=urllib.request.Request(base+'/api/runs',data=b'{}',headers={'Content-Type':'application/json'})
            with self.assertRaises(urllib.error.HTTPError) as error:urllib.request.urlopen(request)
            self.assertEqual(error.exception.code,403)
            request=urllib.request.Request(base+'/api/runs',data=b'{}',headers={'X-Vydra-Token':config['token'],'Origin':'https://example.com'})
            with self.assertRaises(urllib.error.HTTPError) as error:urllib.request.urlopen(request)
            self.assertEqual(error.exception.code,403)
            self.assertEqual(json.load(urllib.request.urlopen(base+'/api/runs')),[])
        finally:server.shutdown();server.server_close()

class GuiWorkerTests(unittest.TestCase):
    def test_worker_preserves_sources_and_generates_report(self):
        import gui_worker
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);source=root/'sample.faa';output=root/'results'
            source.write_text('>original_id description\nMKTAYIAKQRQISFVKSHFSRQ\n')
            state_path=root/'run.json'
            state_path.write_text(json.dumps(dict(id='test',input=str(source),output=str(output),device='auto',offline=True,report=True)))
            def predict(args):
                fasta=Path(args.fasta).read_text();ident=fasta.splitlines()[0][1:]
                Path(args.output).write_text(json.dumps(dict(seq_id=ident,path=['cellular','bacteria'],confidences={'M1':.9,'M2':.8},source_path='combined.faa'))+'\n')
                args._progress_callback(1,1)
                self.assertTrue(args.offline)
            with patch.object(gui_worker,'resolve_model_path',return_value=root/'cached-model'),patch.object(gui_worker,'command_predict',side_effect=predict),patch.dict('os.environ',{},clear=False):
                self.assertEqual(gui_worker.run(state_path),0)
            state=json.loads(state_path.read_text());self.assertEqual(state['status'],'complete')
            row=json.loads((output/'predicciones_completas.jsonl').read_text())
            self.assertEqual(row['source_path'],str(source.resolve()))
            self.assertEqual(row['original_header'],'original_id description')
            self.assertTrue(Path(state['report_path']).is_file())

if __name__=='__main__':unittest.main()
