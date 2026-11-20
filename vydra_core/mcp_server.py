"""Expose the local Vydra run queue over MCP stdio."""

from argparse import ArgumentParser
from http.client import HTTPConnection, HTTPException
from pathlib import Path
import json
import re
import sys
import threading

from local_gui import ENDPOINT_FILE, RunManager, default_state_dir, make_server, publish_endpoint, queue_session
from model_profiles import PROFILES

PROTOCOLS = ('2025-11-25', '2025-06-18', '2025-03-26', '2024-11-05')
RUN_ID = {'type': 'string', 'pattern': '^[0-9a-f]{32}$'}
TOOLS = [
    {
        'name': 'submit_run',
        'description': 'Queue a local protein FASTA analysis. Returns its run ID immediately.',
        'inputSchema': {
            'type': 'object',
            'properties': {
                'input': {'type': 'string', 'description': 'Absolute path to a FASTA file or folder.'},
                'output': {'type': 'string', 'description': 'Absolute path to a new or empty results folder.'},
                'model': {'type': 'string', 'enum': list(PROFILES), 'default': 'prostt5'},
                'device': {'type': 'string', 'enum': ['auto', 'cuda', 'cpu'], 'default': 'auto'},
                'report': {'type': 'boolean', 'default': True},
                'batch_size': {'type': 'integer', 'minimum': 1},
            },
            'required': ['input', 'output'],
            'additionalProperties': False,
        },
    },
    *[
        {
            'name': name,
            'description': description,
            'inputSchema': {
                'type': 'object', 'properties': {'run_id': RUN_ID},
                'required': ['run_id'], 'additionalProperties': False,
            },
            'annotations': {'readOnlyHint': True},
        }
        for name, description in (
            ('get_run_status', 'Read the current phase, progress, elapsed time and phase ETA.'),
            ('get_run_result', 'Get paths to finished results and the M4 agreement counts.'),
        )
    ],
]

STATUS_FIELDS = (
    'status', 'stage', 'model', 'classifier', 'device', 'processed', 'total', 'excluded',
    'chunks_done', 'chunks_total', 'elapsed_seconds', 'phase_rate', 'error',
)


class RemoteQueue:
    def __init__(self, state_dir):
        self.endpoint = state_dir / ENDPOINT_FILE

    def request(self, method, path, values=None):
        try:
            endpoint = json.loads(self.endpoint.read_text(encoding='utf-8'))
            port, token = endpoint['port'], endpoint['token']
            if type(port) is not int or not 1 <= port <= 65535 or not re.fullmatch(r'[A-Za-z0-9_-]{32}', token):
                raise ValueError('Invalid local Vydra endpoint.')
            connection = HTTPConnection('127.0.0.1', port, timeout=10)
            try:
                connection.request(method, path, json.dumps(values) if values is not None else None,
                                   {'Content-Type': 'application/json', 'X-Vydra-Token': token})
                response = connection.getresponse()
                result = json.load(response)
                status = response.status
            finally:
                connection.close()
        except (OSError, HTTPException, ValueError, KeyError, TypeError) as exc:
            raise ValueError('The Vydra queue is unavailable. Open Vydra and try again.') from exc
        if status == 404:
            return None
        if status not in (200, 201):
            raise ValueError(result.get('error', 'The Vydra queue rejected the request.'))
        return result

    def start(self, values):
        return self.request('POST', '/api/runs', values)

    def run(self, ident):
        return self.request('GET', '/api/run/' + ident)


def allowed_path(value, roots):
    if not isinstance(value, str) or not Path(value).is_absolute():
        raise ValueError('Supply an absolute path.')
    path = Path(value).resolve()
    if not any(path.is_relative_to(root) for root in roots):
        raise ValueError('The path is outside the MCP folders configured for this session.')
    return path


def describe(state):
    result = {'run_id': state['id'], **{key: state[key] for key in STATUS_FIELDS if key in state}}
    embedding = state.get('stage') == 'Generating embeddings'
    classifying = state.get('stage') == 'Classifying proteins'
    done, total = ((state.get('chunks_done'), state.get('chunks_total')) if embedding
                   else (state.get('processed'), state.get('total')))
    rate = state.get('phase_rate')
    if state['status'] == 'running' and (embedding or classifying) and rate and done is not None and total is not None:
        result.update(phase_eta_seconds=round(max(0, total - done) / rate, 1),
                      phase_rate_unit='chunks/s' if embedding else 'proteins/s')
    return result


def run_tool(queue, roots, name, args):
    if name == 'submit_run':
        if set(args) - {'input', 'output', 'model', 'device', 'report', 'batch_size'}:
            raise ValueError('Unexpected submit_run argument.')
        source = allowed_path(args.get('input'), roots)
        output = allowed_path(args.get('output'), roots)
        if source.is_dir():
            from folder_inputs import INPUT_EXTENSIONS
            for item in source.rglob('*'):
                if item.suffix.lower() in INPUT_EXTENSIONS and item.is_file():
                    allowed_path(str(item), roots)
        if ('report' in args and type(args['report']) is not bool or
            'batch_size' in args and (type(args['batch_size']) is not int or args['batch_size'] < 1)):
            raise ValueError('Provide a boolean report option and a positive integer batch size.')
        values = {**args, 'input': str(source), 'output': str(output), 'offline': True,
                  'mode': 'folder' if source.is_dir() else 'file'}
        return describe(queue.start(values))

    ident = args.get('run_id')
    if set(args) != {'run_id'} or not isinstance(ident, str) or not re.fullmatch(RUN_ID['pattern'], ident):
        raise ValueError('Supply a valid run ID.')
    state = queue.run(ident)
    if not state:
        raise ValueError('Run not found.')
    output = allowed_path(state['output'], roots)
    allowed_path(state['input'], roots)
    result = describe(state)
    if name == 'get_run_result' and state['status'] in ('complete', 'completed'):
        paths = {'summary_path': output / 'resumen_general.json',
                 'csv_path': output / 'predicciones_completas.csv',
                 'jsonl_path': output / 'predicciones_completas.jsonl'}
        if state.get('report_path'):
            paths['report_path'] = Path(state['report_path'])
        result.update({key: str(allowed_path(str(path), roots)) for key, path in paths.items() if path.is_file()})
        result['summary'] = state.get('result', {}).get('overall', {})
    return result


class McpSession:
    def __init__(self, queue, roots):
        self.queue = queue
        self.roots = roots
        self.initialized = False

    def dispatch(self, message):
        if not isinstance(message, dict) or message.get('jsonrpc') != '2.0' or not isinstance(message.get('method'), str):
            return self.error(None, -32600, 'Invalid request')
        if 'id' not in message:
            return None
        ident, method = message['id'], message['method']
        if type(ident) not in (str, int):
            return self.error(None, -32600, 'Invalid request ID')
        params = message.get('params', {})
        if not isinstance(params, dict):
            return self.error(ident, -32602, 'Expected object parameters')
        if method == 'initialize':
            protocol = params.get('protocolVersion')
            if not isinstance(protocol, str):
                return self.error(ident, -32602, 'Missing protocolVersion')
            self.initialized = True
            result = {'protocolVersion': protocol if protocol in PROTOCOLS else PROTOCOLS[0],
                      'capabilities': {'tools': {}}, 'serverInfo': {'name': 'vydra', 'version': '1.0.0'}}
        elif method == 'ping':
            result = {}
        elif not self.initialized:
            return self.error(ident, -32000, 'Initialize the session first')
        elif method == 'tools/list':
            result = {'tools': TOOLS}
        elif method == 'tools/call':
            name, arguments = params.get('name'), params.get('arguments', {})
            if name not in [tool['name'] for tool in TOOLS] or not isinstance(arguments, dict):
                return self.error(ident, -32602, 'Unknown tool or invalid arguments')
            try:
                data = run_tool(self.queue, self.roots, name, arguments)
                result = {'content': [{'type': 'text', 'text': json.dumps(data, ensure_ascii=False)}]}
            except (OSError, ValueError, TypeError, RuntimeError) as exc:
                result = {'isError': True, 'content': [{'type': 'text', 'text': str(exc)}]}
        else:
            return self.error(ident, -32601, 'Method not found')
        return {'jsonrpc': '2.0', 'id': ident, 'result': result}

    @staticmethod
    def error(ident, code, message):
        return {'jsonrpc': '2.0', 'id': ident, 'error': {'code': code, 'message': message}}

    def serve(self):
        for line in sys.stdin.buffer:
            try:
                message = json.loads(line)
            except (ValueError, UnicodeError):
                response = self.error(None, -32700, 'Invalid JSON')
            else:
                response = self.dispatch(message)
            if response is not None:
                print(json.dumps(response), flush=True)


def configure_parser(parser):
    parser.add_argument('--root', type=Path, action='append', required=True,
                        help='Existing input/output folder allowed for MCP; repeat for multiple folders.')
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--state-dir', type=Path, help='Run history for the Python installation.')
    group.add_argument('--desktop-data-dir', type=Path, help='Data folder of the running Desktop app.')
    return parser


def command_mcp(args):
    roots = [root.expanduser().resolve() for root in args.root]
    if any(not root.is_dir() for root in roots):
        raise ValueError('Each MCP root must be an existing directory.')
    directory = (args.desktop_data_dir / 'runs' if args.desktop_data_dir else args.state_dir or default_state_dir())
    directory = directory.expanduser().resolve()
    if args.desktop_data_dir:
        McpSession(RemoteQueue(directory), roots).serve()
        return 0
    from contextlib import ExitStack
    with ExitStack() as owner:
        try:
            owner.enter_context(queue_session(directory))
        except RuntimeError:
            McpSession(RemoteQueue(directory), roots).serve()
            return 0
        manager = RunManager(directory, queue=True)
        owner.callback(manager.close)
        server = owner.enter_context(make_server(manager))
        owner.enter_context(publish_endpoint(directory, server))
        listener = threading.Thread(target=server.serve_forever, daemon=True)
        listener.start()
        owner.callback(listener.join)
        owner.callback(server.shutdown)
        manager.dispatch()
        McpSession(manager, roots).serve()
    return 0


if __name__ == '__main__':
    parser = configure_parser(ArgumentParser(description=__doc__))
    try:
        raise SystemExit(command_mcp(parser.parse_args()))
    except (OSError, ValueError, RuntimeError) as exc:
        parser.exit(2, f'{exc}\n')
