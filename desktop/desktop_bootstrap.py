"""Prepare Vydra Desktop and supervise its existing local interface."""

import base64
import hashlib
import json
import os
import shutil
import sys
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from http.client import IncompleteRead
from urllib.error import HTTPError
from urllib.request import Request, urlopen


BANK_SIZES = {
    "Struct_prototype_bank.pt": 176507073,
    "Non_Struct_prototype_bank.pt": 1481684953,
}


def setup_event(stage, phase, item, **metrics):
    print("VYDRA_SETUP " + json.dumps(dict(stage=stage, phase=phase, item=item, **metrics)), flush=True)


def fetch_verified(url, target, size, digest, report=None):
    from vydra_cli import sha256_file

    if report is None:
        def report(_phase, _received):
            pass
    if target.is_file() and target.stat().st_size == size:
        report("working", size)
        if sha256_file(target) == digest:
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
                        report("transfer", offset)
                        next_report = time.monotonic() + .8
                        next_notice = time.monotonic() + 10
                        while offset < size:
                            chunk = response.read(min(1024 * 1024, size - offset))
                            if not chunk:
                                break
                            output.write(chunk)
                            offset += len(chunk)
                            now = time.monotonic()
                            if now >= next_report or offset == size:
                                report("transfer", offset)
                                next_report = now + .8
                            if now >= next_notice:
                                print(f"{target.name} · {offset / size:.0%}", flush=True)
                                next_notice = now + 10
            if partial.stat().st_size != size:
                raise OSError("Descarga incompleta.")
            report("working", size)
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
        report("retry", partial.stat().st_size if partial.exists() else 0)
        time.sleep(5 * (2 ** attempt))


M4_PARTS = (
    (536870912, "5dbf3a24bd66b9fc785641683f0f99ad9d467987fc6de61cfbdab7c8865a37ec"),
    (207044955, "ba779cc0a80a3504133695fd5153c78ac4f4a377bbd9f2e3729e9a202d89717f"),
)


def download_stage(stage, items):
    total = sum(size for _, _, size, _ in items)
    completed = 0
    for url, target, size, digest in items:
        def update(phase, received):
            if phase == "working":
                item = f"Verificando {target.name}"
            elif phase == "retry":
                item = f"Reintentando {target.name}"
            else:
                item = target.name
            setup_event(stage, phase, item, received=completed + received, total=total)

        fetch_verified(url, target, size, digest, update)
        completed += size


def prepare_m4_bank():
    from model_profiles import profile_root, verify_manifest
    from profile_install import RELEASE, install_archive

    setup_event("m4", "working", "Buscando el banco M4 en esta carpeta")
    root = profile_root()
    destination = root / "prostt5"
    if destination.exists():
        verify_manifest(destination, "m4_manifest.json", "prostt5")
        setup_event("m4", "done", "Banco M4 reutilizado")
        return
    cache = root.parent / "cache" / "profile-downloads"
    cache.mkdir(parents=True, exist_ok=True)
    root.mkdir(parents=True, exist_ok=True)
    parts = [cache / f"prostt5.tar.zst.part-{i:02d}" for i in range(len(M4_PARTS))]
    limit = 1024**3
    missing_bytes = 0
    for part, (size, _) in zip(parts, M4_PARTS):
        existing = next((p.stat().st_size for p in (part, part.with_name(part.name + ".part"))
                         if p.is_file()), 0)
        missing_bytes += size - existing if existing <= size else size
    if shutil.disk_usage(root).free < limit + missing_bytes:
        raise OSError(f"Se necesitan {limit + missing_bytes:,} bytes libres para el banco M4 en {root}.")
    print("Preparando banco FAISS de M4 para ProstT5…", flush=True)
    download_stage("m4", [(f"{RELEASE}/{part.name}", part, size, digest)
                          for part, (size, digest) in zip(parts, M4_PARTS)])
    setup_event("m4", "working", "Descomprimiendo y comprobando el banco M4")
    install_archive("prostt5", root, parts, limit)
    for part in parts:
        part.unlink()
    setup_event("m4", "done", "Banco M4 preparado")


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


PROSTT5_FILES = {
    "pytorch_model.bin": (5637876077, "b1a9ffcef73280cc57f090ad6446b4116b574b6c75d83ccc32778282f7f00855"),
    "spiece.model": (237990, "74da7b4afcde53faa570114b530c726135bdfcdb813dec3abfb27f9d44db7324"),
}


def verify_prostt5(model_dir):
    from vydra_cli import sha256_file

    for name, (size, digest) in PROSTT5_FILES.items():
        item = model_dir / name
        if not item.is_file() or item.stat().st_size != size or sha256_file(item) != digest:
            raise ValueError(f"El modelo no coincide con la revisión esperada: {item}")


def prostt5_bytes(directory, files):
    # Hugging Face writes the pinned snapshot to its local-dir cache before
    # atomically moving each finished file into the destination.
    cache = directory / ".cache" / "huggingface" / "download"
    received = 0
    for name, (size, digest) in files.items():
        final = directory / name
        fingerprint = base64.urlsafe_b64encode(hashlib.sha1(name.encode()).digest()).decode()
        partial = cache / f"{fingerprint}.{digest}.incomplete"
        for candidate in (final, partial):
            try:
                received += min(candidate.stat().st_size, size)
                break
            except FileNotFoundError:
                continue
    return received


@contextmanager
def model_transfer(directory):
    total = sum(size for size, _ in PROSTT5_FILES.values())
    stop = threading.Event()

    def watch():
        previous = -1
        while not stop.is_set():
            received = prostt5_bytes(directory, PROSTT5_FILES)
            if received != previous:
                setup_event("model", "transfer", "Pesos y tokenizer de ProstT5",
                            total=total, received=received)
                previous = received
            stop.wait(.8)

    thread = threading.Thread(target=watch, daemon=True)
    thread.start()
    try:
        yield
    finally:
        stop.set()
        thread.join()


def prepare(mode):
    from folder_inputs import resolve_model_path
    from vydra_cli import BANKS_DIR, DOWNLOADABLE_ARTIFACTS, RELEASE_BASE_URL, main

    setup_event("libraries", "working", "Comprobando bibliotecas y dispositivo")
    verify_dependencies(mode, check_gpu=True)
    setup_event("libraries", "done", "Bibliotecas disponibles")
    setup_event("references", "working", "Buscando los bancos en la carpeta de datos")
    BANKS_DIR.mkdir(parents=True, exist_ok=True)
    download_stage("references", [(f"{RELEASE_BASE_URL}/{name}", BANKS_DIR / name, BANK_SIZES[name], digest)
                                  for name, digest in DOWNLOADABLE_ARTIFACTS.items()])
    setup_event("references", "done", "Bancos de referencia disponibles")

    setup_event("model", "working", "Buscando la revisión local de ProstT5")
    model_dir = Path(os.environ["VYDRA_PROSTT5_PATH"])
    if not (model_dir / ".vydra-model-ready").is_file() or not (model_dir / "pytorch_model.bin").is_file():
        try:
            resolve_model_path(model_dir, offline=True)
            setup_event("model", "working", "Verificando los pesos locales")
            verify_prostt5(model_dir)
        except (FileNotFoundError, ValueError):
            with model_transfer(model_dir):
                if main(["download-model", "--directory", str(model_dir)]):
                    raise RuntimeError("Falló la preparación de ProstT5.")
            setup_event("model", "working", "Verificando los pesos y el tokenizer")
            resolve_model_path(model_dir, offline=True)
            verify_prostt5(model_dir)
        (model_dir / ".vydra-model-ready").touch()
    resolve_model_path(model_dir, offline=True)
    setup_event("model", "done", "ProstT5 disponible")

    prepare_m4_bank()
    setup_event("verify", "working", "Comprobando modelos y archivos")
    return main(["doctor"])


def serve(state_dir):
    from local_gui import RunManager, make_server, publish_endpoint, queue_session

    with queue_session(state_dir):
        manager = RunManager(Path(state_dir), queue=True)
        with make_server(manager, 0) as server, publish_endpoint(manager.directory, server):
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
