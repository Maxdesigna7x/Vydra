"""Loopback-only, dependency-free GUI server for the installed Vydra bundle."""
from __future__ import annotations
import json
import mimetypes
import os
import re
import secrets
import signal
import subprocess
import sys
import threading
import time
import uuid
import webbrowser
from contextlib import contextmanager
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit, unquote
from folder_inputs import INPUT_EXTENSIONS, write_json
from model_profiles import available_profiles

BASE = Path(__file__).resolve().parent
ACTIVE = {'starting', 'running', 'cancelling'}
STALL_TIMEOUT_SECONDS = 30 * 60


ENDPOINT_FILE = '.mcp-endpoint'


def default_state_dir():
    return Path.home() / '.local' / 'share' / 'vydra' / 'gui'


@contextmanager
def queue_session(state_dir):
    """Only one scheduler may own a run directory at a time."""
    state_dir = Path(state_dir).expanduser().resolve()
    state_dir.mkdir(parents=True, exist_ok=True)
    with (state_dir / '.desktop-queue.lock').open('a+b') as handle:
        try:
            if os.name == 'nt':
                import msvcrt
                handle.seek(0)
                if not handle.read(1):
                    handle.write(b'0')
                    handle.flush()
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise RuntimeError('This run directory already has an active scheduler. Connect to its MCP endpoint.') from exc
        yield


@contextmanager
def publish_endpoint(directory, server):
    endpoint = directory / ENDPOINT_FILE
    write_json(endpoint, {'port': server.server_port, 'token': server.vydra_token})
    try:
        yield
    finally:
        endpoint.unlink(missing_ok=True)


class RunManager:
    def __init__(self, directory, worker=None, *, queue=False):
        self.directory = Path(directory).expanduser().resolve()
        self.directory.mkdir(parents=True, exist_ok=True)
        self.worker = Path(worker) if worker else BASE / 'gui_worker.py'
        self.lock = threading.RLock()
        self.processes = {}
        self.monitors = {}
        self.cancelled = set()
        self.queue = queue
        self.closing = False
        for path in self.directory.glob('*.json'):
            try:
                state = json.loads(path.read_text(encoding='utf-8'))
                if state.get('status') in ACTIVE:
                    try:
                        pid = int((self.directory / (state['id'] + '.pid')).read_text())
                        if pid < 1:
                            raise ValueError('Invalid PID')
                        if os.name == 'nt':
                            # Windows os.kill(pid, 0) calls TerminateProcess.
                            import ctypes
                            from ctypes import wintypes

                            kernel = ctypes.WinDLL('kernel32', use_last_error=True)
                            kernel.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
                            kernel.OpenProcess.restype = wintypes.HANDLE
                            kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
                            handle = kernel.OpenProcess(0x1000, False, pid)
                            if not handle:
                                raise OSError('Worker is unavailable.')
                            try:
                                kernel.GetExitCodeProcess.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
                                status = wintypes.DWORD()
                                if not kernel.GetExitCodeProcess(handle, ctypes.byref(status)) or status.value != 259:
                                    raise OSError('Worker has exited.')
                            finally:
                                kernel.CloseHandle(handle)
                        else:
                            os.kill(pid, 0)
                    except (OSError, ValueError, KeyError):
                        state.update(status='interrupted', stage='Interrupted', error='The previous process exited before completing. Resume this run to reuse saved checkpoints.')
                        write_json(path, state)
            except (OSError, ValueError, KeyError):
                continue

    def runs(self):
        result = []
        with self.lock:
            for path in self.directory.glob('*.json'):
                try:
                    state = json.loads(path.read_text(encoding='utf-8'))
                    if state['id'] in self.cancelled and state['status'] in ACTIVE:
                        state['status'] = 'cancelling'
                        state['stage'] = 'Cancelling'
                    result.append(state)
                except (OSError, ValueError, KeyError):
                    continue
        return sorted(result, key=lambda row: row['created_at'], reverse=True)

    def run(self, ident):
        if not re.fullmatch(r'[0-9a-f]{32}', ident):
            return None
        with self.lock:
            try:
                state = json.loads((self.directory / (ident + '.json')).read_text(encoding='utf-8'))
            except FileNotFoundError:
                return None
            if ident in self.cancelled and state['status'] in ACTIVE:
                state.update(status='cancelling', stage='Cancelling')
            return state

    def start(self, values, *, legacy_classifier=None):
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
        device = values.get('device', 'auto')
        if device not in ('auto', 'cuda', 'cpu'):
            raise ValueError('Unknown device.')
        profile = values.get('model') or 'prostt5'
        classifier = legacy_classifier or 'both'
        available = {item['id']: item for item in available_profiles()}
        if profile not in available or not available[profile]['installed']:
            raise ValueError('Install the selected model profile before starting.')
        if classifier not in ('both', 'mlp', 'faiss') or (classifier != 'mlp' and not available[profile]['faiss']):
            raise ValueError('Install the FAISS M4 bank for the selected model to compare MLP and FAISS.')
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
        resume = legacy_classifier is not None and bool(values.get('resume'))
        with self.lock:
            if self.closing:
                raise ValueError('Vydra is closing.')
            rows = self.runs()
            pending = [row for row in rows if row['status'] in ACTIVE or row['status'] == 'queued']
            if not self.queue and (pending or self.processes):
                raise ValueError('Another run is active. Wait for it to finish or cancel it.')
            self._check_destination(output, resume)
            for row in pending:
                reserved = Path(row['output'])
                if output == reserved or output in reserved.parents or reserved in output.parents:
                    raise ValueError('Choose a results folder outside the folders reserved by active or queued tasks.')
            ident = uuid.uuid4().hex
            state = dict(id=ident, status='queued', stage='Queued', mode=mode, input=str(source), output=str(output),
                         device=device, model=profile, classifier=classifier, offline=bool(values.get('offline')),
                         report=bool(values.get('report', True)), batch_size=batch, resume=resume,
                         created_at=datetime.now(timezone.utc).isoformat(), total=None, processed=None)
            if not self.queue:
                self._launch(state)
                return state
            write_json(self.directory / (ident + '.json'), state)
            launched = self.dispatch()
            if launched and launched['id'] == ident:
                return launched
            return state

    @staticmethod
    def _check_destination(output, resume):
        if output.exists() and (not output.is_dir() or (any(output.iterdir()) and not resume)):
            raise ValueError('The output folder must be new or empty. Existing results are never overwritten.')
        if resume and not (output / 'preparation_checkpoint.json').is_file():
            raise ValueError('No prepared checkpoint in this output folder.')

    def _launch(self, state):
        ident = state['id']
        path = self.directory / (ident + '.json')
        state.update(status='starting', stage='Starting', started_timestamp=time.time())
        write_json(path, state)
        try:
            with (self.directory / (ident + '.log')).open('wb') as log:
                proc = subprocess.Popen([sys.executable, '-u', str(self.worker), str(path)], stdout=log,
                                        stderr=subprocess.STDOUT, start_new_session=os.name != 'nt', cwd=BASE)
        except OSError as exc:
            state.update(status='failed', stage='Failed', error=str(exc))
            write_json(path, state)
            raise
        self.processes[ident] = proc
        try:
            # The process owns the run file after launch; keep PID in a separate file.
            (self.directory / (ident + '.pid')).write_text(str(proc.pid))
        finally:
            monitor = threading.Thread(target=self._monitor, args=(ident, proc), daemon=True)
            self.monitors[ident] = monitor
            monitor.start()

    def dispatch(self):
        with self.lock:
            if not self.queue or self.closing or self.processes:
                return None
            rows = self.runs()
            if any(row['status'] in ACTIVE for row in rows):
                return None
            for state in reversed(rows):
                if state['status'] != 'queued':
                    continue
                try:
                    if not Path(state['input']).exists():
                        raise ValueError('The queued input is no longer available.')
                    self._check_destination(Path(state['output']), state['resume'])
                    self._launch(state)
                except (OSError, ValueError) as exc:
                    if state['id'] in self.processes:
                        return state
                    state.update(status='failed', stage='Failed', error=str(exc),
                                 finished_at=datetime.now(timezone.utc).isoformat())
                    write_json(self.directory / (state['id'] + '.json'), state)
                    continue
                return state
        return None

    def resume(self, ident):
        with self.lock:
            state = next((r for r in self.runs() if r['id'] == ident), None)
            if not state or state['status'] not in ('cancelled', 'failed', 'interrupted'):
                raise ValueError('Only an interrupted, cancelled or failed run can be resumed.')
            values = {key: state.get(key) for key in ('mode', 'input', 'output', 'device', 'offline', 'report', 'batch_size', 'model', 'classifier')}
            values['resume'] = True
            return self.start(values, legacy_classifier=state.get('classifier') or 'mlp')

    @staticmethod
    def stalled(state, now=None):
        working = (state.get('stage') == 'Classifying proteins' or
                   (state.get('stage') == 'Generating embeddings' and state.get('batch_size_active', 0) > 0))
        since = state.get('work_started_at')
        return bool(state.get('status') == 'running' and working and since and
                    (time.time() if now is None else now) - since >= STALL_TIMEOUT_SECONDS)

    def _monitor(self, ident, proc):
        timeout_error = None
        path = self.directory / (ident + '.json')
        while True:
            try:
                code = proc.wait(timeout=5)
                break
            except subprocess.TimeoutExpired:
                try:
                    current = json.loads(path.read_text(encoding='utf-8'))
                except (OSError, ValueError):
                    continue
                if self.stalled(current):
                    timeout_error = ('Stopped after 30 minutes without completing a model batch or protein classification. '
                                     'Saved checkpoints were retained. Review the log and Resume run to retry the unfinished work.')
                    try:
                        if os.name == 'nt':
                            proc.terminate()
                        else:
                            os.killpg(proc.pid, signal.SIGTERM)
                    except ProcessLookupError:
                        pass
                    self._kill_later(proc)
                    code = proc.wait()
                    break
        with self.lock:
            try:
                state = json.loads(path.read_text(encoding='utf-8'))
                if ident in self.cancelled:
                    state.update(status='cancelled', stage='Cancelled', error='Checkpoints were retained. Resume this run to continue.')
                elif timeout_error:
                    state.update(status='failed', stage='Stopped: no progress', error=timeout_error)
                elif state['status'] in ACTIVE:
                    state.update(status='failed', stage='Failed', error=f'Inference process exited with code {code}. See the execution log.')
                state['elapsed_seconds'] = round(time.time() - state['started_timestamp'], 1)
                state['finished_at'] = datetime.now(timezone.utc).isoformat()
                write_json(path, state)
            finally:
                self.processes.pop(ident, None)
                self.monitors.pop(ident, None)
                self.cancelled.discard(ident)
                self.dispatch()

    def cancel(self, ident):
        with self.lock:
            if self.queue:
                queued = next((row for row in self.runs() if row['id'] == ident and row['status'] == 'queued'), None)
                if queued:
                    queued.update(status='cancelled', stage='Cancelled',
                                  finished_at=datetime.now(timezone.utc).isoformat())
                    write_json(self.directory / (ident + '.json'), queued)
                    self.dispatch()
                    return 'cancelled'
            proc = self.processes.get(ident)
            if not proc or proc.poll() is not None:
                raise ValueError('This run is no longer active in this server session.')
            self.cancelled.add(ident)
            if os.name == 'nt':
                proc.terminate()
            else:
                os.killpg(proc.pid, signal.SIGTERM)
            threading.Thread(target=self._kill_later, args=(proc,), daemon=True).start()
            return 'cancelling'

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
        with self.lock:
            self.closing = True
            processes = dict(self.processes)
            monitors = tuple(self.monitors.values())
        for ident in processes:
            try:
                self.cancel(ident)
            except (ValueError, ProcessLookupError):
                pass
        for proc in processes.values():
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                pass
        for monitor in monitors:
            monitor.join(timeout=2)


def make_server(manager, port=0):
    token = secrets.token_urlsafe(24)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def send(self, code, data, content_type='application/json'):
            body = json.dumps(data).encode() if content_type == 'application/json' and not isinstance(data, bytes) else data
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
                    config = {'token': token, 'home': str(Path.home()), 'cwd': str(Path.cwd()),
                              'python': sys.executable, 'windows': os.name == 'nt', 'models': available_profiles()}
                    if desktop_mode := os.environ.get('VYDRA_DESKTOP_MODE'):
                        config['desktop'] = {'mode': desktop_mode, 'windows': os.name == 'nt'}
                    return self.send(200, config)
                if request.path == '/api/runs':
                    manager.dispatch()
                    return self.send(200, manager.runs())
                if request.path.startswith('/api/run/'):
                    if not self.allowed(mutation=True):
                        return self.send(403, {'error': 'Local request token required.'})
                    state = manager.run(request.path.rsplit('/', 1)[-1])
                    return self.send(200, state) if state else self.send(404, {'error': 'Run not found.'})
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
                if request.path.startswith('/reports/'):
                    parts = request.path.split('/', 3)
                    run = next((r for r in manager.runs() if r['id'] == parts[2]), None)
                    if not run or run['status'] not in ('complete', 'completed') or not run.get('report_path'):
                        return self.send(404, {'error': 'No report is available for this run.'})
                    report = Path(run['report_path']).resolve()
                    output = Path(run['output']).resolve()
                    root = report.parent
                    relative = unquote(parts[3]) if len(parts) > 3 else ''
                    target = (root / relative).resolve() if relative else report
                    if (root != output and output not in root.parents) or (target != root and root not in target.parents):
                        return self.send(403, {'error': 'Report path is outside its results folder.'})
                    if not target.is_file():
                        return self.send(404, {'error': 'Report file is missing.'})
                    mime = mimetypes.guess_type(target.name)[0] or 'application/octet-stream'
                    return self.send(200, target.read_bytes(), mime)
                static = {'/': ('index.html', 'text/html; charset=utf-8'), '/gui.js': ('gui.js', 'text/javascript; charset=utf-8'), '/gui.css': ('gui.css', 'text/css; charset=utf-8'),
                          '/run-queue.js': ('run-queue.js', 'text/javascript; charset=utf-8'),
                          '/run-queue.css': ('run-queue.css', 'text/css; charset=utf-8'),
                          '/vydra.png': ('vydra.png', 'image/png')}
                if request.path in static:
                    name, mime = static[request.path]
                    asset = BASE / 'gui' / name
                    if name == 'vydra.png' and not asset.is_file():
                        asset = BASE.parent / 'desktop' / 'assets' / name
                    return self.send(200, asset.read_bytes(), mime)
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
                if self.path.startswith('/api/resume/'):
                    return self.send(201, manager.resume(self.path.rsplit('/', 1)[-1]))
                if self.path.startswith('/api/cancel/'):
                    return self.send(200, {'status': manager.cancel(self.path.rsplit('/', 1)[-1])})
                if self.path == '/api/check':
                    result = subprocess.run([sys.executable, str(BASE / 'vydra_cli.py'), 'doctor'], capture_output=True, text=True, timeout=120, cwd=BASE)
                    return self.send(200, {'ok': result.returncode == 0, 'log': result.stdout + result.stderr})
                return self.send(404, {'error': 'Not found.'})
            except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
                self.send(400, {'error': str(exc)})

    server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    server.vydra_token = token
    return server


@contextmanager
def run_service(state_dir, port=0):
    """Own the local queue and HTTP service for either frontend host."""
    with queue_session(state_dir):
        manager = RunManager(state_dir, queue=True)
        with make_server(manager, port) as server, publish_endpoint(manager.directory, server):
            manager.dispatch()
            try:
                yield server
            finally:
                manager.close()


def serve(port=0, open_browser=True, state_dir=None):
    if not 0 <= port <= 65535:
        raise ValueError('Port must be between 0 and 65535.')
    with run_service(state_dir or default_state_dir(), port) as server:
        url = f'http://127.0.0.1:{server.server_port}/'
        print(f'Vydra local interface: {url}\nKeep this terminal open. Press Ctrl+C to stop the server.', flush=True)
        if open_browser:
            threading.Timer(.3, lambda: webbrowser.open(url)).start()
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
    return 0
