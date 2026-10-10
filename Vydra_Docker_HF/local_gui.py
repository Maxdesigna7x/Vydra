"""Loopback-only, dependency-free GUI server for the installed Vydra bundle."""
from __future__ import annotations
import json
import os
import secrets
import signal
import subprocess
import sys
import threading
import time
import uuid
import webbrowser
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from folder_inputs import INPUT_EXTENSIONS, write_json

BASE = Path(__file__).resolve().parent
ACTIVE = {'starting', 'running', 'cancelling'}


class RunManager:
    def __init__(self, directory, worker=None):
        self.directory = Path(directory).expanduser().resolve()
        self.directory.mkdir(parents=True, exist_ok=True)
        self.worker = Path(worker) if worker else BASE / 'gui_worker.py'
        self.lock = threading.RLock()
        self.processes = {}
        self.cancelled = set()
        for path in self.directory.glob('*.json'):
            try:
                state = json.loads(path.read_text())
                if state.get('status') in ACTIVE:
                    try:
                        pid = int((self.directory / (state['id'] + '.pid')).read_text())
                        if pid < 1:
                            raise ValueError('Invalid PID')
                        os.kill(pid, 0)
                    except (OSError, ValueError, KeyError):
                        state.update(status='interrupted', stage='Interrupted', error='The previous process exited before completing. Start a new run in a new output folder.')
                        write_json(path, state)
            except (OSError, ValueError, KeyError):
                continue

    def runs(self):
        result = []
        with self.lock:
            for path in self.directory.glob('*.json'):
                try:
                    state = json.loads(path.read_text())
                    if state['id'] in self.cancelled and state['status'] in ACTIVE:
                        state['status'] = 'cancelling'
                        state['stage'] = 'Cancelling'
                    result.append(state)
                except (OSError, ValueError, KeyError):
                    continue
        return sorted(result, key=lambda row: row['created_at'], reverse=True)

    def start(self, values):
        source = Path(str(values.get('input', ''))).expanduser().resolve()
        output_text = str(values.get('output', '')).strip()
        if not str(values.get('input', '')).strip() or not source.exists():
            raise ValueError('Select an existing input file or folder.')
        mode = values.get('mode', 'folder')
        if mode not in ('folder', 'file') or (mode == 'folder' and not source.is_dir()) or (mode == 'file' and (not source.is_file() or source.suffix.lower() not in INPUT_EXTENSIONS)):
            raise ValueError('Input must match the selected type: a folder or a FASTA file.')
        if not output_text:
            raise ValueError('Choose a new output folder.')
        output = Path(output_text).expanduser().resolve()
        if output == source or (source.is_dir() and source in output.parents):
            raise ValueError('Choose an output folder outside the input folder.')
        if output.exists() and (not output.is_dir() or any(output.iterdir())):
            raise ValueError('The output folder must be new or empty. Existing results are never overwritten.')
        device = values.get('device', 'auto')
        if device not in ('auto', 'cuda', 'cpu'):
            raise ValueError('Unknown device.')
        batch = values.get('batch_size')
        if batch not in (None, ''):
            try:
                batch = int(batch)
            except (TypeError, ValueError):
                raise ValueError('Batch size must be a positive integer.')
            if batch < 1:
                raise ValueError('Batch size must be a positive integer.')
        else:
            batch = None
        with self.lock:
            if any(row['status'] in ACTIVE for row in self.runs()):
                raise ValueError('Another run is active. Wait for it to finish or cancel it.')
            ident = uuid.uuid4().hex
            state = dict(id=ident, status='starting', stage='Starting', mode=mode, input=str(source), output=str(output),
                         device=device, offline=bool(values.get('offline')), report=bool(values.get('report', True)),
                         batch_size=batch, created_at=datetime.now(timezone.utc).isoformat(),
                         started_timestamp=time.time(), total=None, processed=None)
            path = self.directory / (ident + '.json')
            write_json(path, state)
            log = (self.directory / (ident + '.log')).open('wb')
            try:
                proc = subprocess.Popen([sys.executable, '-u', str(self.worker), str(path)], stdout=log,
                                        stderr=subprocess.STDOUT, start_new_session=os.name != 'nt', cwd=BASE)
            except OSError as exc:
                state.update(status='failed', stage='Failed', error=str(exc))
                write_json(path, state)
                raise
            finally:
                log.close()
            self.processes[ident] = proc
            # The process owns the run file after launch; keep PID in a separate file.
            (self.directory / (ident + '.pid')).write_text(str(proc.pid))
            threading.Thread(target=self._monitor, args=(ident, proc), daemon=True).start()
            return state

    def _monitor(self, ident, proc):
        code = proc.wait()
        with self.lock:
            path = self.directory / (ident + '.json')
            state = json.loads(path.read_text())
            if ident in self.cancelled:
                state.update(status='cancelled', stage='Cancelled', error='Partial files were retained. Use a new output folder to retry.')
            elif state['status'] in ACTIVE:
                state.update(status='failed', stage='Failed', error=f'Inference process exited with code {code}. See the execution log.')
            state['elapsed_seconds'] = round(time.time() - state['started_timestamp'], 1)
            state['finished_at'] = datetime.now(timezone.utc).isoformat()
            write_json(path, state)
            self.processes.pop(ident, None)

    def cancel(self, ident):
        with self.lock:
            proc = self.processes.get(ident)
            if not proc or proc.poll() is not None:
                raise ValueError('This run is no longer active in this server session.')
            self.cancelled.add(ident)
            if os.name == 'nt':
                proc.terminate()
            else:
                os.killpg(proc.pid, signal.SIGTERM)
            threading.Thread(target=self._kill_later, args=(proc,), daemon=True).start()

    @staticmethod
    def _kill_later(proc):
        try:
            proc.wait(timeout=8)
        except subprocess.TimeoutExpired:
            if os.name == 'nt':
                proc.kill()
            else:
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass

    def close(self):
        for ident in list(self.processes):
            try:
                self.cancel(ident)
            except (ValueError, ProcessLookupError):
                pass
        for proc in list(self.processes.values()):
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                pass


def make_server(manager, port=0):
    token = secrets.token_urlsafe(24)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def send(self, code, data, content_type='application/json'):
            body = json.dumps(data).encode() if content_type == 'application/json' else data
            self.send_response(code)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.end_headers()
            self.wfile.write(body)

        def allowed(self, mutation=False):
            expected = f'127.0.0.1:{self.server.server_port}'
            origin = self.headers.get('Origin')
            return self.headers.get('Host') == expected and (not origin or origin == 'http://' + expected) and (not mutation or self.headers.get('X-Vydra-Token') == token)

        def do_GET(self):
            if not self.allowed():
                return self.send(403, {'error': 'Local requests only.'})
            request = urlsplit(self.path)
            try:
                if request.path == '/api/config':
                    return self.send(200, {'token': token, 'home': str(Path.home()), 'cwd': str(Path.cwd()), 'python': sys.executable})
                if request.path == '/api/runs':
                    return self.send(200, manager.runs())
                if request.path == '/api/browse':
                    raw = parse_qs(request.query).get('path', [str(Path.home())])[0]
                    path = Path(raw).expanduser().resolve()
                    if not path.is_dir():
                        raise ValueError('Folder does not exist.')
                    entries = sorted(path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
                    return self.send(200, {'path': str(path), 'parent': str(path.parent), 'entries': [
                        {'name': p.name, 'path': str(p), 'directory': p.is_dir()} for p in entries
                        if p.is_dir() or p.suffix.lower() in INPUT_EXTENSIONS][:500]})
                if request.path.startswith('/api/log/'):
                    ident = request.path.rsplit('/', 1)[-1]
                    if not any(r['id'] == ident for r in manager.runs()):
                        return self.send(404, {'error': 'Run not found.'})
                    with (manager.directory / (ident + '.log')).open('rb') as stream:
                        stream.seek(0, 2)
                        stream.seek(max(0, stream.tell() - 65536))
                        log = stream.read().decode('utf-8', errors='replace')
                    return self.send(200, {'log': log})
                static = {'/': ('index.html', 'text/html; charset=utf-8'), '/gui.js': ('gui.js', 'text/javascript; charset=utf-8'), '/gui.css': ('gui.css', 'text/css; charset=utf-8')}
                if request.path in static:
                    name, mime = static[request.path]
                    return self.send(200, (BASE / 'gui' / name).read_bytes(), mime)
                return self.send(404, {'error': 'Not found.'})
            except (OSError, ValueError) as exc:
                self.send(400, {'error': str(exc)})

        def do_POST(self):
            if not self.allowed(mutation=True):
                return self.send(403, {'error': 'Local request token required.'})
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 16384:
                    raise ValueError('Invalid request size.')
                values = json.loads(self.rfile.read(length))
                if not isinstance(values, dict):
                    raise ValueError('Expected an object.')
                if self.path == '/api/runs':
                    return self.send(201, manager.start(values))
                if self.path.startswith('/api/cancel/'):
                    manager.cancel(self.path.rsplit('/', 1)[-1])
                    return self.send(200, {'status': 'cancelling'})
                if self.path == '/api/check':
                    result = subprocess.run([sys.executable, str(BASE / 'vydra_cli.py'), 'doctor'], capture_output=True, text=True, timeout=120, cwd=BASE)
                    return self.send(200, {'ok': result.returncode == 0, 'log': result.stdout + result.stderr})
                return self.send(404, {'error': 'Not found.'})
            except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
                self.send(400, {'error': str(exc)})

    return ThreadingHTTPServer(('127.0.0.1', port), Handler)


def serve(port=0, open_browser=True, state_dir=None):
    if not 0 <= port <= 65535:
        raise ValueError('Port must be between 0 and 65535.')
    manager = RunManager(state_dir or Path.home() / '.local' / 'share' / 'vydra' / 'gui')
    server = make_server(manager, port)
    url = f'http://127.0.0.1:{server.server_port}/'
    print(f'Vydra local interface: {url}\nKeep this terminal open. Press Ctrl+C to stop the server.', flush=True)
    if open_browser:
        threading.Timer(.3, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        manager.close()
    return 0
