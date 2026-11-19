import hashlib
import sys
import tempfile
import threading
import unittest
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "vydra_core"))
from desktop_bootstrap import fetch_verified


@contextmanager
def server(payload, requests, *, supports_range=True):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            requested = self.headers.get("Range")
            requests.append(requested)
            start = int(requested[6:-1]) if requested and supports_range else 0
            self.send_response(206 if start else 200)
            if start:
                self.send_header("Content-Range", f"bytes {start}-{len(payload) - 1}/{len(payload)}")
            self.send_header("Content-Length", str(len(payload) - start))
            self.end_headers()
            self.wfile.write(payload[start:])

        def log_message(self, *_):
            pass

    with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as http:
        worker = threading.Thread(target=http.serve_forever)
        worker.start()
        try:
            yield f"http://127.0.0.1:{http.server_port}/"
        finally:
            http.shutdown()
            worker.join()


class SetupDownloads(unittest.TestCase):
    def test_resume_and_reuse_verified_file(self):
        payload = b"0123456789" * 100
        calls = []
        with tempfile.TemporaryDirectory() as directory, server(payload, calls) as url:
            target = Path(directory, "bank.pt")
            partial = target.with_suffix(".pt.part")
            partial.write_bytes(payload[:73])
            digest = hashlib.sha256(payload).hexdigest()
            fetch_verified(url, target, len(payload), digest)
            fetch_verified(url, target, len(payload), digest)
            self.assertEqual(calls, ["bytes=73-"])
            self.assertEqual(target.read_bytes(), payload)
            self.assertFalse(partial.exists())

    def test_full_response_replaces_partial_if_range_unsupported(self):
        payload = b"content"
        with tempfile.TemporaryDirectory() as directory, server(payload, [], supports_range=False) as url:
            target = Path(directory, "bank.pt")
            target.with_suffix(".pt.part").write_bytes(b"broken")
            fetch_verified(url, target, len(payload), hashlib.sha256(payload).hexdigest())
            self.assertEqual(target.read_bytes(), payload)

    def test_discard_wrong_hash(self):
        with tempfile.TemporaryDirectory() as directory, server(b"bad", []) as url:
            target = Path(directory, "bank.pt")
            with patch("desktop_bootstrap.time.sleep"), self.assertRaisesRegex(ValueError, "SHA-256"):
                fetch_verified(url, target, 3, hashlib.sha256(b"abc").hexdigest())
            self.assertFalse(target.exists())
            self.assertFalse(target.with_suffix(".pt.part").exists())
