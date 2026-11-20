"""Prepare Vydra Desktop and supervise its existing local interface."""

from contextlib import contextmanager
import os
import shutil
import sys
import threading
import time
from pathlib import Path
from http.client import IncompleteRead
from urllib.error import HTTPError
from urllib.request import Request, urlopen


BANK_SIZES = {
    "Struct_prototype_bank.pt": 176507073,
    "Non_Struct_prototype_bank.pt": 1481684953,
}


def fetch_verified(url, target, size, digest):
    from vydra_cli import sha256_file

    if target.is_file() and target.stat().st_size == size and sha256_file(target) == digest:
        print(f"Verificado: {target.name}.", flush=True)
        return
    partial = target.with_name(target.name + ".part")
    if target.is_file():
        if partial.exists():
            target.unlink()
        else:
            target.replace(partial)
    for attempt in range(4):
        offset = partial.stat().st_size if partial.exists() else 0
        if offset > size:
            partial.unlink()
            offset = 0
        try:
            if offset < size:
                if shutil.disk_usage(target.parent).free <= size - offset:
                    raise OSError(f"Espacio insuficiente para {target.name}.")
                headers = {"Range": f"bytes={offset}-"} if offset else {}
                with urlopen(Request(url, headers=headers), timeout=120) as response:
                    append = response.status == 206
                    if append:
                        if response.headers.get("Content-Range") != f"bytes {offset}-{size - 1}/{size}":
                            raise ValueError("El servidor devolvió un tramo de descarga incorrecto.")
                    else:
                        offset = 0
                    with partial.open("ab" if append else "wb") as output:
                        print(f"Descargando {target.name} desde {offset:,} de {size:,} bytes.", flush=True)
                        next_notice = time.monotonic() + 10
                        while offset < size:
                            chunk = response.read(min(1024 * 1024, size - offset))
                            if not chunk:
                                break
                            output.write(chunk)
                            offset += len(chunk)
                            if time.monotonic() >= next_notice:
                                print(f"{target.name} · {offset / size:.0%}", flush=True)
                                next_notice = time.monotonic() + 10
            if partial.stat().st_size != size:
                raise OSError("Descarga incompleta.")
            if sha256_file(partial) != digest:
                partial.unlink()
                raise ValueError(f"Falló la verificación SHA-256 de {target.name}.")
            partial.replace(target)
            return
        except HTTPError as error:
            if error.code not in {408, 429, 500, 502, 503, 504} or attempt == 3:
                raise
        except (OSError, ValueError, IncompleteRead):
            if attempt == 3:
                raise
        time.sleep(5 * (2 ** attempt))


def verify_dependencies(mode, check_gpu):
    import faiss
    import numpy as np
    import pandas
    import sentencepiece
    import torch
    from transformers import T5EncoderModel, T5Tokenizer
    from gpu_faiss import build_index, faiss_device, search_index, select_device

    print(f"PyTorch {torch.__version__} · FAISS {faiss.__version__} · pandas {pandas.__version__}", flush=True)
    if mode == "cuda" and not torch.version.cuda:
        raise RuntimeError("El paquete de PyTorch carece de CUDA.")
    if mode == "cuda" and sys.platform == "linux" and not hasattr(faiss, "StandardGpuResources"):
        raise RuntimeError("El paquete de FAISS carece de GPU.")
    backend = select_device(mode) if check_gpu else torch.device("cpu")
    index_backend = faiss_device(backend)
    vectors = np.eye(2, dtype=np.float32)
    index = build_index(vectors, index_backend.index, device=index_backend)
    scores, indices = search_index(index, vectors)
    if not np.array_equal(indices[:, 0], [0, 1]) or not np.allclose(scores[:, 0], [1, 1]):
        raise RuntimeError("Falló la prueba de FAISS.")
    if backend.type == "cuda":
        if torch.tensor([2.0], device=backend).square().item() != 4:
            raise RuntimeError("Falló la prueba de cálculo CUDA.")
    print(f"Prueba de dependencias correcta. PyTorch: {backend}. FAISS: {index_backend}.", flush=True)


def verify_prostt5(model_dir):
    from vydra_cli import sha256_file

    expected = {
        "pytorch_model.bin": (5637876077, "b1a9ffcef73280cc57f090ad6446b4116b574b6c75d83ccc32778282f7f00855"),
        "spiece.model": (237990, "74da7b4afcde53faa570114b530c726135bdfcdb813dec3abfb27f9d44db7324"),
    }
    for name, (size, digest) in expected.items():
        item = model_dir / name
        if not item.is_file() or item.stat().st_size != size or sha256_file(item) != digest:
            raise ValueError(f"El modelo no coincide con la revisión esperada: {item}")


def prepare(mode):
    from folder_inputs import resolve_model_path
    from vydra_cli import BANKS_DIR, DOWNLOADABLE_ARTIFACTS, RELEASE_BASE_URL, main

    verify_dependencies(mode, check_gpu=True)
    BANKS_DIR.mkdir(parents=True, exist_ok=True)
    for filename, digest in DOWNLOADABLE_ARTIFACTS.items():
        fetch_verified(f"{RELEASE_BASE_URL}/{filename}", BANKS_DIR / filename, BANK_SIZES[filename], digest)
    model_dir = Path(os.environ["VYDRA_PROSTT5_PATH"])
    if not (model_dir / ".vydra-model-ready").is_file() or not (model_dir / "pytorch_model.bin").is_file():
        print("Preparando ProstT5. Se reutilizarán los archivos completos y los parciales de la descarga.", flush=True)
        try:
            resolve_model_path(model_dir, offline=True)
            verify_prostt5(model_dir)
        except (FileNotFoundError, ValueError):
            if main(["download-model", "--directory", str(model_dir)]):
                raise RuntimeError("Falló la preparación de ProstT5.")
            resolve_model_path(model_dir, offline=True)
            verify_prostt5(model_dir)
        (model_dir / ".vydra-model-ready").touch()
    resolve_model_path(model_dir, offline=True)
    return main(["doctor"])


@contextmanager
def desktop_session(state_dir):
    """Only one desktop scheduler may own a run directory at a time."""
    state_dir.mkdir(parents=True, exist_ok=True)
    with (state_dir / '.desktop-queue.lock').open('a+b') as handle:
        try:
            if os.name == 'nt':
                import msvcrt
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise RuntimeError('La cola de esta carpeta de datos ya está abierta en otra ventana.') from exc
        yield


def serve(state_dir):
    from local_gui import RunManager, make_server

    with desktop_session(Path(state_dir)):
        manager = RunManager(Path(state_dir), queue=True)
        with make_server(manager, 0) as server:
            manager.dispatch()

            # Electron owns the write end. EOF also covers crashes and forced exits.
            def watch_parent():
                sys.stdin.buffer.read()
                server.shutdown()

            threading.Thread(target=watch_parent, daemon=True).start()
            print(f"VYDRA_READY http://127.0.0.1:{server.server_port}/", flush=True)
            try:
                server.serve_forever()
            finally:
                manager.close()


if __name__ == "__main__":
    action, argument = sys.argv[1:]
    if action == "serve":
        serve(argument)
    elif action == "imports":
        verify_dependencies(argument, check_gpu=False)
    elif action == "prepare":
        raise SystemExit(prepare(argument))
    else:
        raise SystemExit(f"Unknown action: {action}")
