import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'vydra_core'))
from local_gui import RunManager, make_server, publish_endpoint
from mcp_server import describe


class McpQueueTests(unittest.TestCase):
    def test_stdio_joins_running_queue_and_limits_roots(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            allowed = root / 'allowed'
            allowed.mkdir()
            source = allowed / 'protein.faa'
            source.write_text('>synthetic\nMKTLL\n')
            worker = root / 'worker.py'
            worker.write_text('import time\ntime.sleep(30)\n')
            manager = RunManager(root / 'runs', worker, queue=True)
            self.addCleanup(manager.close)
            catalog = [{'id': 'prostt5', 'installed': True, 'faiss': True}]
            with patch('local_gui.available_profiles', return_value=catalog):
                existing = manager.start(dict(mode='file', input=str(source), output=str(allowed / 'first')))
                self.assertEqual(existing['status'], 'starting')
                with make_server(manager) as server, publish_endpoint(manager.directory, server):
                    listener = threading.Thread(target=server.serve_forever, daemon=True)
                    listener.start()
                    try:
                        payload = [
                            dict(id=1, method='initialize', params={'protocolVersion': '2025-11-25'}),
                            dict(method='notifications/initialized'),
                            dict(id=2, method='tools/list'),
                            dict(id=3, method='tools/call', params={'name': 'submit_run', 'arguments': {
                                'input': str(source), 'output': str(allowed / 'second')}}),
                            dict(id=4, method='tools/call', params={'name': 'submit_run', 'arguments': {
                                'input': str(source), 'output': str(root / 'outside')}}),
                            dict(id=5, method='tools/call', params={'name': 'get_run_status', 'arguments': {
                                'run_id': existing['id']}}),
                        ]
                        messages = '\n'.join(json.dumps(dict(jsonrpc='2.0', **m)) for m in payload) + '\n'
                        proc = subprocess.run([sys.executable, str(ROOT / 'vydra'), 'mcp',
                                               '--desktop-data-dir', str(root), '--root', str(allowed)],
                                              input=messages, capture_output=True, text=True, timeout=10, check=True)
                    finally:
                        server.shutdown()
                        listener.join()
                replies = {row['id']: row['result'] for row in map(json.loads, proc.stdout.splitlines())}
                self.assertEqual(list(replies), [1, 2, 3, 4, 5])
                self.assertEqual(replies[1]['protocolVersion'], '2025-11-25')
                self.assertEqual(len(replies[2]['tools']), 3)
                submitted = json.loads(replies[3]['content'][0]['text'])
                self.assertEqual(submitted['status'], 'queued')
                self.assertEqual(manager.run(submitted['run_id'])['classifier'], 'both')
                self.assertTrue(replies[4]['isError'])
                observed = json.loads(replies[5]['content'][0]['text'])
                self.assertEqual(observed['run_id'], existing['id'])
                self.assertEqual(observed['status'], 'starting')
                manager.close()

    def test_phase_eta_uses_chunks_during_embedding(self):
        result = describe({'id': 'test', 'status': 'running', 'stage': 'Generating embeddings',
                           'processed': 1, 'total': 9, 'chunks_done': 5, 'chunks_total': 15, 'phase_rate': 2})
        self.assertEqual(result['phase_eta_seconds'], 5)
        self.assertEqual(result['phase_rate_unit'], 'chunks/s')
