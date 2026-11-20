import json
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'vydra_core'))
from local_gui import RunManager


class DesktopQueueTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.source = self.root / 'input.faa'
        self.source.write_text('>fixture\nAAAA\n')
        self.worker = self.root / 'worker.py'
        self.worker.write_text("""
import json, sys, time
from pathlib import Path
state_path = Path(sys.argv[1])
state = json.loads(state_path.read_text())
gate = Path(state['output'] + '.go')
while not gate.exists():
    time.sleep(.02)
state.update(status='completed', stage='Completed')
staging = state_path.with_suffix('.tmp')
staging.write_text(json.dumps(state))
staging.replace(state_path)
""")
        self.manager = RunManager(self.root / 'state', self.worker, queue=True)
        self.addCleanup(self.manager.close)

    def submit(self, name):
        return self.manager.start(dict(mode='file', input=str(self.source), output=str(self.root / name)))

    def release(self, name):
        (self.root / (name + '.go')).touch()

    def wait_for(self, identifier, status):
        deadline = time.monotonic() + 6
        while time.monotonic() < deadline:
            current = next(row for row in self.manager.runs() if row['id'] == identifier)
            if current['status'] == status:
                return current
            time.sleep(.03)
        self.fail(f'Task {identifier} did not reach {status}: {current}')

    def test_fifo_and_output_reservation(self):
        first = self.submit('first')
        second = self.submit('second')
        third = self.submit('third')
        self.assertEqual(first['status'], 'starting')
        self.assertEqual(second['status'], 'queued')
        self.assertEqual(third['status'], 'queued')
        with self.assertRaisesRegex(ValueError, 'reserved'):
            self.submit('second/subfolder')
        self.release('first')
        self.wait_for(second['id'], 'starting')
        self.assertEqual(self.wait_for(third['id'], 'queued')['stage'], 'Queued')
        self.release('second')
        self.wait_for(third['id'], 'starting')
        self.release('third')
        self.wait_for(third['id'], 'completed')

    def test_cancellation_and_restart_preserve_the_queue(self):
        first = self.submit('first')
        removed = self.submit('removed')
        last = self.submit('last')
        self.assertEqual(self.manager.cancel(removed['id']), 'cancelled')
        self.manager.close()
        self.wait_for(first['id'], 'cancelled')
        self.wait_for(last['id'], 'queued')
        self.manager = RunManager(self.root / 'state', self.worker, queue=True)
        self.addCleanup(self.manager.close)
        self.manager.dispatch()
        self.wait_for(last['id'], 'starting')
        self.release('last')
        self.wait_for(last['id'], 'completed')
        self.assertFalse((self.manager.directory / (removed['id'] + '.log')).exists())

    def test_invalid_queued_output_does_not_block_later_tasks(self):
        self.submit('first')
        invalid = self.submit('became-occupied')
        tail = self.submit('tail')
        output = self.root / 'became-occupied'
        output.mkdir()
        (output / 'keep').touch()
        self.release('first')
        failure = self.wait_for(invalid['id'], 'failed')
        self.assertIn('never overwritten', failure['error'])
        self.assertTrue((output / 'keep').is_file())
        self.wait_for(tail['id'], 'starting')
        self.release('tail')
        self.wait_for(tail['id'], 'completed')


if __name__ == '__main__':
    unittest.main()
