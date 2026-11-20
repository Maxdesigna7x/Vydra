"""Durable, fixed-size per-protein embeddings and an incremental prediction journal."""
from __future__ import annotations
import hashlib
import json
import os
import shutil
import sqlite3
import time
from pathlib import Path


def atomic_json(path, value):
    path = Path(path)
    temp = path.with_name(path.name + '.tmp')
    with temp.open('w', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    temp.replace(path)
    if os.name != 'nt':
        fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


def estimate_storage(count, sequence_bytes=0, dimension=1024, report=True):
    # Final vectors have fixed size. Partial windows use a separate journal.
    partial_allowance = sequence_bytes * 4 + count * 256 + 16 * 1024**2
    embeddings = count * dimension * 4
    integrity = count * 32
    # Variable-size annotations/exports: an allowance, not an upper bound.
    outputs = count * 64 * 1024 + sequence_bytes * 6
    reserve = max(256 * 1024**2, (embeddings + integrity + outputs) // 10)
    return dict(sequences=count, dimension=dimension, dtype='float32',
                embedding_bytes=embeddings, integrity_bytes=integrity,
                checkpoint_bytes=embeddings + integrity,
                partial_chunk_allowance_bytes=partial_allowance,
                estimated_results_bytes=outputs,
                report_allowance_bytes=64 * 1024**2 if report else 0,
                reserve_bytes=reserve,
                estimated_total_bytes=embeddings + integrity + partial_allowance + outputs + reserve + (64 * 1024**2 if report else 0),
                note='Final embedding size is exact; partial chunk journal, predictions, reports and filesystem overhead are estimates. Model downloads are excluded.')


def human_bytes(value):
    return f'{value / 1024**3:.2f} GiB ({value:,} bytes)'


def check_space(path, required):
    path = Path(path).resolve()
    while not path.exists():
        path = path.parent
    free = shutil.disk_usage(path).free
    if free < required:
        raise OSError(f'Insufficient disk space: need {human_bytes(required)} additional free space; available {human_bytes(free)} at {path}')
    return free


def identity_for(engine, records, text=None, embedding_path=None):
    digest = hashlib.sha256()
    if text is not None:
        digest.update(text.encode('utf-8'))
    else:
        with Path(embedding_path).open('rb') as stream:
            for block in iter(lambda: stream.read(1024**2), b''):
                digest.update(block)
    # Compare actual model/reference contents, not only filenames or mtimes.
    assets = []
    selected_profile = getattr(engine, 'active_profile', None)
    if selected_profile is None or selected_profile.id == 'prostt5':
        model = Path(str(getattr(engine, 'MODEL_NAME', '')))
        if model.is_dir():
            assets.extend(p for p in model.rglob('*') if p.is_file())
        for directory in (getattr(engine, 'WEIGHTS_DIR', None), getattr(engine, 'ARTIFACTS_DIR', None)):
            if directory and Path(directory).is_dir():
                assets.extend(p for p in Path(directory).iterdir() if p.is_file())
    assets.extend(Path(__file__).parent / name for name in
                  ('engine.py', 'model_artifacts.py', 'gpu_faiss.py', 'biological_context.py', 'vydra_cli.py', 'checkpoints.py'))
    if getattr(engine, 'active_profile', None) is not None:
        assets.extend(Path(__file__).parent / name for name in ('profile_runtime.py', 'model_profiles.py'))
    asset_hashes = {}
    for path in sorted(set(assets)):
        h = hashlib.sha256()
        with path.open('rb') as stream:
            for block in iter(lambda: stream.read(1024**2), b''):
                h.update(block)
        asset_hashes[str(path.resolve())] = h.hexdigest()
    return dict(schema=1, input_sha256=digest.hexdigest(), count=len(records),
                dimension=getattr(engine, 'EMB_DIM', 1024), assets=asset_hashes,
                model=str(getattr(engine, 'MODEL_NAME', '')), device=str(engine.device),
                chunk_length=getattr(engine, 'MAX_PROT_LEN', 2048),
                chunk_overlap=getattr(engine, 'CHUNK_OVERLAP', 512))


# Previous runtime revisions with equivalent single-method output. Inputs,
# configuration, device and every model/reference fingerprint must still match.
LEGACY_RUNTIME_HASHES = {
    'engine.py': {
        'a09dc4b97bbbb65853692d5f1aea2c9ddfa6e512427c01b0d29e02e4c403a773',
        'b285edc82fa70e98f8cb1633b6ecc86a403eb296b703f6ec207a4540fc4d9742',
    },
    'vydra_cli.py': {
        '0bc29fe70e6a3f1ce2256a21d2cc2a41388b14c4cc924a6af5cb0e759395aff8',
        'f0fa48a81f05e796fdb814df2c7027be165dd147316b3dae7a16ad5efac16000',
    },
    'checkpoints.py': {
        '2ff3ceb6b756c54c02e1f5b2310ccfba8e01b6c4d34d4f9c84dda3388beaadd5',
        '7cf1f03a81cfb7bae2d4708206b26727cc6ab99d472f2d8a4dd6f74a6efab42a',
    },
    'profile_runtime.py': {'277b7fdb917f6b8ce6b002cdb714b200df63aa07223a01bf574b6f82f018b8a7'},
}


def compatible_identity(saved, current):
    if saved == current:
        return True
    old, new = dict(saved), dict(current)
    old_assets, new_assets = old.pop('assets', {}), new.pop('assets', {})
    if old != new or not old_assets:
        return False
    runtime = Path(__file__).parent.resolve()
    # Desktop copies its core into a versioned folder beside the previous one.
    if old_assets.keys() != new_assets.keys() and runtime.parent.parent.name == 'app':
        previous_roots = [path.parent for key in old_assets if (path := Path(key)).name == 'engine.py'
                          and path.parent.name == runtime.name and path.parent.parent.parent == runtime.parent.parent]
        if len(previous_roots) == 1:
            previous = previous_roots[0]
            old_assets = {
                str(runtime / Path(key).relative_to(previous)) if Path(key).is_relative_to(previous) else key: value
                for key, value in old_assets.items()
            }
    if old_assets.keys() != new_assets.keys():
        return False
    return all(value == new_assets[path] or (
        current.get('classifier') != 'both' and Path(path).parent == runtime
        and value in LEGACY_RUNTIME_HASHES.get(Path(path).name, ())
    ) for path, value in old_assets.items())


class Checkpoint:
    def __init__(self, directory, identity, estimate, resume=False, embeddings=True):
        self.directory = Path(directory).resolve()
        self.directory.mkdir(parents=True, exist_ok=True)
        self.lock = (self.directory / 'lock').open('a+b')
        self.vectors = self.hashes = None
        self.chunks = None
        self.last_saved_at = None
        try:
            if os.name == 'nt':
                import msvcrt
                self.lock.seek(0)
                if not self.lock.read(1):
                    self.lock.write(b'0'); self.lock.flush()
                self.lock.seek(0)
                msvcrt.locking(self.lock.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            meta = self.directory / 'identity.json'
            saved_identity = json.loads(meta.read_text()) if resume and meta.is_file() else None
            if resume:
                if saved_identity is None or not compatible_identity(saved_identity, identity):
                    raise ValueError('Checkpoint does not match input, models, references, device or inference code. Use a new output/checkpoint directory.')
            elif meta.exists() or any(p.name != 'lock' for p in self.directory.iterdir()):
                raise ValueError('Checkpoint already exists. Use --resume or a new output/checkpoint directory.')
            self.count, self.dimension = identity['count'], identity['dimension']
            allocated = sum(p.stat().st_size for p in self.directory.iterdir() if p.is_file()) if resume else 0
            estimate = dict(estimate)
            estimate['available_bytes'] = check_space(self.directory, max(0, estimate['estimated_total_bytes'] - allocated))
            atomic_json(self.directory / 'storage_estimate.json', estimate)
            if not resume:
                atomic_json(meta, identity)
            initialized = (self.directory / "initialized.json").is_file()
            if embeddings:
                import numpy as np
                for name, size in (('embeddings.f32', self.count * self.dimension * 4), ('embedding_sha256.bin', self.count * 32)):
                    path = self.directory / name
                    if resume and initialized:
                        if not path.is_file() or path.stat().st_size != size:
                            raise ValueError(f'Missing or invalid checkpoint file: {path}')
                    else:
                        with path.open('wb') as stream:
                            # Reserve physical space where supported; fail before computing.
                            if hasattr(os, 'posix_fallocate'):
                                os.posix_fallocate(stream.fileno(), 0, size)
                            else:
                                stream.truncate(size)
                            stream.flush(); os.fsync(stream.fileno())
                self.vectors = np.memmap(self.directory / 'embeddings.f32', dtype='float32', mode='r+', shape=(self.count, self.dimension))
                self.hashes = np.memmap(self.directory / 'embedding_sha256.bin', dtype='uint8', mode='r+', shape=(self.count, 32))
            self.chunks = sqlite3.connect(self.directory / 'partial_chunks.sqlite3')
            self.chunks.execute('PRAGMA synchronous=FULL')
            self.chunks.execute('CREATE TABLE IF NOT EXISTS chunks (record_idx INTEGER, chunk_idx INTEGER, vector BLOB NOT NULL, digest BLOB NOT NULL, PRIMARY KEY(record_idx, chunk_idx))')
            self.chunks.commit()
            if resume and saved_identity != identity:
                atomic_json(meta, identity)
            if not initialized:
                atomic_json(self.directory / "initialized.json", {"ready": True})
        except BaseException:
            self.close()
            raise

    def completed(self):
        import numpy as np
        done = np.zeros(self.count, dtype=bool)
        for index in range(self.count):
            stored = self.hashes[index].tobytes()
            if stored != bytes(32):
                done[index] = stored == hashlib.sha256(self.vectors[index].tobytes()).digest()
                if not done[index]:
                    self.hashes[index] = 0  # A torn/corrupt vector is recomputed.
        return done

    def save_embeddings(self, items):
        import numpy as np
        if not items:
            return
        for index, vector in items:
            vector = np.asarray(vector, dtype='float32')
            if vector.shape != (self.dimension,) or not np.isfinite(vector).all():
                raise ValueError('Invalid checkpoint embedding')
            self.vectors[index] = vector
        self.vectors.flush()
        self._sync('embeddings.f32')
        for index, _ in items:
            self.hashes[index] = np.frombuffer(hashlib.sha256(self.vectors[index].tobytes()).digest(), dtype='uint8')
        self.hashes.flush()
        self._sync('embedding_sha256.bin')

    def load_chunks(self, completed):
        """Only verified windows of unfinished proteins are reusable."""
        import numpy as np
        result = {}
        invalid = []
        for record, chunk, blob, digest in self.chunks.execute('SELECT * FROM chunks'):
            if not 0 <= record < self.count or chunk < 0:
                raise ValueError('Invalid chunk checkpoint index')
            if completed[record]:
                invalid.append((record, chunk))
                continue
            if len(blob) != self.dimension * 4 or hashlib.sha256(blob).digest() != digest:
                invalid.append((record, chunk))
                continue
            vector = np.frombuffer(blob, dtype='float32').copy()
            if not np.isfinite(vector).all():
                invalid.append((record, chunk))
                continue
            result[(record, chunk)] = vector
        with self.chunks:
            self.chunks.executemany('DELETE FROM chunks WHERE record_idx=? AND chunk_idx=?', invalid)
        return result

    def save_chunks(self, items):
        import numpy as np
        rows = []
        for record, chunk, vector in items:
            vector = np.asarray(vector, dtype='float32')
            if not 0 <= record < self.count or chunk < 0 or vector.shape != (self.dimension,) or not np.isfinite(vector).all():
                raise ValueError('Invalid checkpoint chunk')
            blob = vector.tobytes()
            rows.append((record, chunk, blob, hashlib.sha256(blob).digest()))
        check_space(self.directory, len(rows) * (self.dimension * 4 + 256) + 16 * 1024**2)
        with self.chunks:
            self.chunks.executemany('INSERT OR REPLACE INTO chunks VALUES (?, ?, ?, ?)', rows)

    def discard_chunks(self, records):
        # Final embeddings are fsynced before their partial journal is removed.
        with self.chunks:
            self.chunks.executemany('DELETE FROM chunks WHERE record_idx=?', [(i,) for i in records])

    def save_progress(self, **values):
        self.last_saved_at = time.time()
        atomic_json(self.directory / 'progress.json', dict(saved_at=self.last_saved_at, **values))

    def _sync(self, name):
        with (self.directory / name).open('rb') as stream:
            os.fsync(stream.fileno())

    def predictions(self):
        path = self.directory / 'predictions.jsonl'
        rows = []
        if not path.exists():
            return rows
        with path.open('r+b') as stream:
            while True:
                offset = stream.tell()
                line = stream.readline()
                if not line:
                    break
                if not line.endswith(b'\n'):
                    stream.truncate(offset); stream.flush(); os.fsync(stream.fileno())
                    break
                item = json.loads(line)
                if item['index'] != len(rows) or len(rows) >= self.count:
                    raise ValueError('Invalid prediction checkpoint order')
                rows.append(item['row'])
        return rows

    def save_predictions(self, rows, start):
        payload = ''.join(json.dumps({'index': start + i, 'row': row}, ensure_ascii=False, allow_nan=False) + '\n' for i, row in enumerate(rows))
        check_space(self.directory, len(payload.encode('utf-8')) + 16 * 1024**2)
        with (self.directory / 'predictions.jsonl').open('a', encoding='utf-8') as stream:
            stream.write(payload); stream.flush(); os.fsync(stream.fileno())

    def close(self):
        if getattr(self, 'chunks', None) is not None:
            self.chunks.close()
            self.chunks = None
        for name in ('vectors', 'hashes'):
            array = getattr(self, name, None)
            if array is not None:
                array._mmap.close()
                setattr(self, name, None)
        if getattr(self, 'lock', None):
            self.lock.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
