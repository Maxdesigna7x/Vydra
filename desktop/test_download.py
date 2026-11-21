import hashlib
import base64
import sys
import tempfile
import threading
import unittest
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "vydra_core"))
from desktop_bootstrap import BANK_SIZES, M4_PARTS, fetch_verified, prepare_data, prostt5_bytes


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
            progress = []
            fetch_verified(url, target, len(payload), digest, lambda *event: progress.append(event))
            fetch_verified(url, target, len(payload), digest)
            self.assertEqual(progress[0], ("transfer", 73))
            self.assertEqual(progress[-1], ("working", len(payload)))
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

    def test_model_meter_uses_the_matching_snapshot_partial(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cache = root / ".cache" / "huggingface" / "download"
            cache.mkdir(parents=True)
            name = "pytorch_model.bin"
            key = base64.urlsafe_b64encode(hashlib.sha1(name.encode()).digest()).decode()
            (cache / f"{key}.wrong.incomplete").write_bytes(b"old payload")
            (cache / f"{key}.current.incomplete").write_bytes(b"part")
            self.assertEqual(prostt5_bytes(root, {name: (10, "current")}), 4)
            (root / name).write_bytes(b"0123456789")
            self.assertEqual(prostt5_bytes(root, {name: (10, "current")}), 10)

    def test_data_tracks_reference_and_m4_banks_with_one_total(self):
        class Disk:
            free = 100 * 1024**3

        def download(_url, target, size, _digest, report):
            target.touch()
            report("transfer", 0)
            report("working", size)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch("model_profiles.profile_root", return_value=root / "profiles"), \
                 patch("vydra_cli.BANKS_DIR", root / "artifacts"), \
                 patch("desktop_bootstrap.shutil.disk_usage", return_value=Disk()), \
                 patch("desktop_bootstrap.fetch_verified", side_effect=download), \
                 patch("desktop_bootstrap.setup_event") as events, \
                 patch("profile_install.install_archive") as extract:
                prepare_data()

            progress = [call.kwargs for call in events.call_args_list if "total" in call.kwargs]
            total = sum(BANK_SIZES.values()) + sum(size for size, _ in M4_PARTS)
            self.assertEqual({sample["total"] for sample in progress}, {total})
            self.assertEqual(progress[-1]["received"], total)
            self.assertTrue(all(call.args[0] == "data" for call in events.call_args_list))
            self.assertEqual(extract.call_args.args[:2], ("prostt5", root / "profiles"))
