"""Local ProstT5, hierarchical classifiers, and CPU/GPU FAISS inference engine."""
from __future__ import annotations

import gc
import json
import os
import threading
from dataclasses import dataclass
from functools import wraps
from pathlib import Path

os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from transformers import T5EncoderModel, T5Tokenizer

try:
    from . import gpu_faiss
except ImportError:
    import gpu_faiss


BASE_DIR = Path(__file__).resolve().parent
ARTIFACTS_DIR = BASE_DIR / "artifacts"
WEIGHTS_DIR = BASE_DIR / "models/mlp_weights"
STRUCTURAL_PROTOTYPE_BANK = ARTIFACTS_DIR / "Struct_prototype_bank.pt"
NON_STRUCTURAL_PROTOTYPE_BANK = ARTIFACTS_DIR / "Non_Struct_prototype_bank.pt"
CLUSTER_TAXONOMY_CSV = ARTIFACTS_DIR / "cluster_taxonomy_summary.csv"
VIRAL_EUK_CLASS_METADATA_CSV = ARTIFACTS_DIR / "viral_euk_class_metadata.csv"
THRESHOLD_CONFIG_JSON = ARTIFACTS_DIR / "recommended_thresholds_config.json"

MODEL_NAME = "Rostlab/ProstT5"
EMB_DIM = 1024
MAX_PROT_LEN = 2048
CHUNK_OVERLAP = 512
EMB_NORM_EPS = 1e-12

MODEL_NAMES = [
    "M1_L1_viral_vs_cellular",
    "M2_cellular_3_clases",
    "M3_viral_phage_vs_euk",
    "M4_viral_euk_978_clases",
    "M5_phage_structural_vs_non",
    "M6_structural_10_clases",
]

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

# Embedding and classification stages must not overlap across local inference threads:
# a finished stage releases the encoder before FAISS starts using the VRAM.
inference_lock = threading.RLock()


def serialized_inference(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        with inference_lock:
            return function(*args, **kwargs)
    return wrapped


class MLP(nn.Module):
    def __init__(self, in_dim: int = EMB_DIM, num_classes: int = 2):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(in_dim, 512),
            nn.BatchNorm1d(512),
            nn.ReLU(),
            nn.Dropout(0.3),
            nn.Linear(512, 256),
            nn.BatchNorm1d(256),
            nn.ReLU(),
            nn.Dropout(0.2),
            nn.Linear(256, num_classes),
        )

    def forward(self, x):
        return self.net(x)


@dataclass
class SequenceRecord:
    seq_id: str
    sequence: str
    original_length: int
    chunked: bool


def load_json(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"Missing artifact: {path}")
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def normalize_matrix(x: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(x, axis=1, keepdims=True)
    return (x / np.clip(norms, EMB_NORM_EPS, None)).astype(np.float32)


def require_faiss_gpu():
    """Validate the selected backend (name retained for runtime compatibility)."""
    return gpu_faiss.require_backend(device)


def build_faiss_index(x: np.ndarray):
    selected = device.index if device.type == "cuda" else None
    return gpu_faiss.build_index(x, selected, device=device)


def load_cluster_annotations(path: Path) -> dict[tuple[str, str, int], dict]:
    if not path.exists():
        print(f"Missing cluster taxonomy summary: {path}")
        return {}
    df = pd.read_csv(path).fillna("")
    annotations = {}
    for _, row in df.iterrows():
        key = (str(row["dataset_type"]), str(row["class_name"]), int(row["cluster_id"]))
        annotations[key] = {
            "n_sequences": int(row["n_sequences"]),
            "metadata_coverage": row.get("metadata_coverage", ""),
            "representative_seq_id": row.get("representative_seq_id", ""),
            "representative_accession": row.get("representative_accession", ""),
            "representative_product": row.get("representative_product", ""),
            "representative_organism": row.get("representative_organism", ""),
            "representative_virus_name": row.get("representative_virus_name", ""),
            "representative_genus": row.get("representative_genus", ""),
            "representative_family": row.get("representative_family", ""),
            "representative_host": row.get("representative_host", ""),
            "representative_source_fasta": row.get("representative_source_fasta", ""),
            "length_known": row.get("length_known", ""),
            "min_length": row.get("min_length", ""),
            "max_length": row.get("max_length", ""),
            "mean_length": row.get("mean_length", ""),
            "std_length": row.get("std_length", ""),
            "families_in_cluster": row.get("families_in_cluster", ""),
            "genera_in_cluster": row.get("genera_in_cluster", ""),
            "hosts_in_cluster": row.get("hosts_in_cluster", ""),
            "virus_names_in_cluster": row.get("virus_names_in_cluster", ""),
            "products_in_cluster": row.get("products_in_cluster", ""),
            "organisms_in_cluster": row.get("organisms_in_cluster", ""),
            "best_taxonomic_level": row.get("best_taxonomic_level", ""),
            "confidence": row.get("confidence", ""),
            "dominant_virus_name": row.get("dominant_virus_name", ""),
            "virus_name_purity": row.get("virus_name_purity", ""),
            "virus_name_coverage": row.get("virus_name_coverage", ""),
            "dominant_genus": row.get("dominant_genus", ""),
            "genus_purity": row.get("genus_purity", ""),
            "genus_coverage": row.get("genus_coverage", ""),
            "dominant_family": row.get("dominant_family", ""),
            "family_purity": row.get("family_purity", ""),
            "family_coverage": row.get("family_coverage", ""),
            "dominant_host": row.get("dominant_host", ""),
            "host_purity": row.get("host_purity", ""),
            "host_coverage": row.get("host_coverage", ""),
        }
    return annotations


def load_viral_euk_class_metadata(path: Path) -> dict[str, dict]:
    if not path.exists():
        print(f"Missing Viral_Euk class metadata: {path}")
        return {}
    df = pd.read_csv(path).fillna("")
    metadata = {}
    for _, row in df.iterrows():
        class_number = str(int(row["class_number"]))
        metadata[class_number] = {
            "class_number": class_number,
            "cluster_rep_sequence_accession": row.get("cluster_rep_sequence_accession", ""),
            "family_label_ncbi_2021": row.get("family_label_ncbi_2021", ""),
            "families_in_class_2021": row.get("families_in_class_2021", ""),
            "family_label_ncbi_2023": row.get("family_label_ncbi_2023", ""),
            "sequences_per_class": row.get("sequences_per_class", ""),
            "sequences_percent": row.get("sequences_percent", ""),
            "max_length": row.get("max_length", ""),
            "mean_length": row.get("mean_length", ""),
            "std_length": row.get("std_length", ""),
            "kmers_per_class": row.get("kmers_per_class", ""),
            "kmers_percent": row.get("kmers_percent", ""),
            "protein_description": row.get("protein_description", ""),
            "protein_function_class": row.get("protein_function_class", ""),
            "host": row.get("host", ""),
            "molecule_type": row.get("molecule_type", ""),
            "genus": row.get("genus", ""),
        }
    return metadata


def empty_viral_euk_class_metadata() -> dict:
    return {
        "class_number": "",
        "cluster_rep_sequence_accession": "",
        "family_label_ncbi_2021": "",
        "families_in_class_2021": "",
        "family_label_ncbi_2023": "",
        "sequences_per_class": "",
        "sequences_percent": "",
        "max_length": "",
        "mean_length": "",
        "std_length": "",
        "kmers_per_class": "",
        "kmers_percent": "",
        "protein_description": "",
        "protein_function_class": "",
        "host": "",
        "molecule_type": "",
        "genus": "",
    }


def get_viral_euk_class_metadata(class_name: str) -> dict:
    return viral_euk_class_metadata.get(str(class_name), empty_viral_euk_class_metadata())


def biological_label(annotation: dict) -> str:
    level = str(annotation.get("best_taxonomic_level", "") or "")
    if level == "genus" and annotation.get("dominant_genus"):
        return f"genus:{annotation['dominant_genus']}"
    if level == "family" and annotation.get("dominant_family"):
        return f"family:{annotation['dominant_family']}"
    if level == "host" and annotation.get("dominant_host"):
        return f"host:{annotation['dominant_host']}"
    return level or "unannotated"


def build_prototype_bank(bank_path: Path, dataset_type: str) -> dict[str, dict]:
    if not bank_path.exists():
        raise FileNotFoundError(f"Missing prototype bank artifact: {bank_path}")
    raw = torch.load(bank_path, map_location="cpu", weights_only=False)
    if not isinstance(raw, dict) or not raw:
        raise ValueError(f"Expected non-empty prototype bank dict in {bank_path}")

    bank: dict[str, dict] = {}

    for class_name, entry in raw.items():
        class_name = str(class_name)
        if not isinstance(entry, dict):
            continue

        vectors = entry.get("prototypes", entry.get("centroids"))
        cluster_ids = entry.get("cluster_ids")
        seq_ids = entry.get("seq_ids", [])
        if vectors is None or cluster_ids is None:
            raise ValueError(f"Prototype bank class '{class_name}' is missing vectors or cluster_ids")

        x = np.asarray(vectors, dtype=np.float32)
        if x.ndim != 2 or x.shape[1] != EMB_DIM:
            raise ValueError(f"Invalid prototype matrix for {class_name}: {x.shape}")

        cluster_ids = np.asarray(cluster_ids, dtype=np.int32)
        seq_ids = np.asarray(seq_ids, dtype=object)
        if len(cluster_ids) != len(x):
            raise ValueError(f"cluster_ids length mismatch for {class_name}: {len(cluster_ids)} vs {len(x)}")
        if len(seq_ids) == 0:
            seq_ids = np.asarray([f"{class_name}_prototype_{i}" for i in range(len(x))], dtype=object)
        elif len(seq_ids) != len(x):
            raise ValueError(f"seq_ids length mismatch for {class_name}: {len(seq_ids)} vs {len(x)}")

        valid = cluster_ids >= 0
        x = x[valid]
        cluster_ids = cluster_ids[valid]
        seq_ids = seq_ids[valid]
        if len(x) == 0:
            continue

        x = normalize_matrix(x)
        bank[class_name] = {
            "dataset_type": dataset_type,
            "seq_ids": seq_ids,
            "cluster_ids": cluster_ids,
            "index": build_faiss_index(x),
            "n_vectors": int(len(seq_ids)),
            "prototype_threshold": entry.get("prototype_threshold", ""),
            "prototype_source": entry.get("prototype_source", ""),
        }
        print(f"Loaded prototype bank {dataset_type}/{class_name}: {len(seq_ids)} prototypes")
        del x

    del raw
    gc.collect()
    return bank


models: dict[str, nn.Module] | None = None
label_classes: dict[str, list[str]] | None = None
models_lock = threading.Lock()


def load_models() -> tuple[dict[str, nn.Module], dict[str, list[str]]]:
    global models, label_classes
    if models is not None and label_classes is not None:
        return models, label_classes

    with models_lock:
        if models is not None and label_classes is not None:
            return models, label_classes

        print("Loading MLP weights...")
        require_faiss_gpu()
        class_map = load_json(ARTIFACTS_DIR / "label_classes.json")
        loaded: dict[str, nn.Module] = {}
        for model_name in MODEL_NAMES:
            weight_path = WEIGHTS_DIR / f"{model_name}.pth"
            if not weight_path.exists():
                raise FileNotFoundError(f"Missing model weight: {weight_path}")
            classes = class_map[model_name]
            model = MLP(num_classes=len(classes)).to(device)
            state = torch.load(weight_path, map_location=device, weights_only=False)
            model.load_state_dict(state)
            model.eval()
            loaded[model_name] = model
        models = loaded
        label_classes = class_map
        return models, label_classes

cluster_annotations = load_cluster_annotations(CLUSTER_TAXONOMY_CSV)
viral_euk_class_metadata = load_viral_euk_class_metadata(VIRAL_EUK_CLASS_METADATA_CSV)
threshold_config = load_json(THRESHOLD_CONFIG_JSON) if THRESHOLD_CONFIG_JSON.exists() else {}
thresholds_by_class = threshold_config.get("thresholds_by_class", {})

structural_prototype_bank: dict[str, dict] | None = None
non_structural_prototype_bank: dict[str, dict] | None = None
prototype_bank_lock = threading.Lock()

t5_tokenizer: T5Tokenizer | None = None
t5_model: T5EncoderModel | None = None


def get_structural_prototype_bank() -> dict[str, dict]:
    global structural_prototype_bank
    if structural_prototype_bank is None:
        with prototype_bank_lock:
            if structural_prototype_bank is None:
                print("Loading structural FAISS prototype bank...")
                structural_prototype_bank = build_prototype_bank(STRUCTURAL_PROTOTYPE_BANK, "structural")
    return structural_prototype_bank


def get_non_structural_prototype_bank() -> dict[str, dict]:
    global non_structural_prototype_bank
    if not NON_STRUCTURAL_PROTOTYPE_BANK.exists():
        print(f"Missing non-structural prototype bank: {NON_STRUCTURAL_PROTOTYPE_BANK}. Skipping non-structural FAISS assignment.")
        non_structural_prototype_bank = {}
        return non_structural_prototype_bank
    if non_structural_prototype_bank is None:
        with prototype_bank_lock:
            if non_structural_prototype_bank is None:
                print("Loading non-structural FAISS prototype bank...")
                non_structural_prototype_bank = build_prototype_bank(
                    NON_STRUCTURAL_PROTOTYPE_BANK,
                    "non_structural",
                )
    return non_structural_prototype_bank


@serialized_inference
def preload_inference_artifacts() -> None:
    require_faiss_gpu()
    load_models()
    get_structural_prototype_bank()
    get_non_structural_prototype_bank()


@serialized_inference
def load_prost_t5() -> tuple[T5Tokenizer, T5EncoderModel]:
    global t5_tokenizer, t5_model
    if t5_model is None:
        require_faiss_gpu()
        print("Loading Rostlab/ProstT5...")
        if t5_tokenizer is None:
            t5_tokenizer = T5Tokenizer.from_pretrained(MODEL_NAME, do_lower_case=False)
        t5_model = T5EncoderModel.from_pretrained(
            MODEL_NAME,
            low_cpu_mem_usage=False,
            torch_dtype=torch.float32,
            device_map=None,
        )
        if any(param.is_meta for param in t5_model.parameters()):
            raise RuntimeError(
                "ProstT5 loaded with meta parameters. "
                "This is usually a transformers/runtime incompatibility, not a Python version issue."
            )
        t5_model = t5_model.to(device)
        if device.type == "cuda":
            t5_model = t5_model.half()
        t5_model.eval()
    return t5_tokenizer, t5_model


@serialized_inference
def release_prost_t5() -> None:
    """Release encoder weights, including references held by error tracebacks."""
    global t5_model
    if t5_model is None:
        return
    model = t5_model
    t5_model = None
    # Moving weights also releases VRAM when a caller/traceback holds the model.
    model.to("cpu")
    del model
    gc.collect()
    if device.type == "cuda":
        torch.cuda.empty_cache()
    print("ProstT5 released from memory before classification/FAISS.")


def canonicalize_sequence(seq: str) -> str:
    seq = seq.strip().upper().replace(" ", "")
    return seq.translate(str.maketrans({"U": "X", "Z": "X", "O": "X", "B": "X"}))


def parse_fasta_text(text: str) -> list[SequenceRecord]:
    records = []
    header = "query_1"
    chunks: list[str] = []
    auto_idx = 1
    has_header = False

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith(">"):
            has_header = True
            if chunks:
                seq = canonicalize_sequence("".join(chunks))
                records.append(SequenceRecord(header, seq, len(seq), len(seq) > MAX_PROT_LEN))
                chunks = []
            header = line[1:].split()[0] or f"query_{auto_idx}"
            auto_idx += 1
        else:
            chunks.append(line)

    if chunks:
        seq = canonicalize_sequence("".join(chunks))
        records.append(SequenceRecord(header if has_header else "query_1", seq, len(seq), len(seq) > MAX_PROT_LEN))
    return [r for r in records if r.sequence]


def chunk_sequence(seq: str, chunk_len: int = MAX_PROT_LEN, overlap: int = CHUNK_OVERLAP) -> list[str]:
    if len(seq) <= chunk_len:
        return [seq]
    overlap = min(overlap, chunk_len - 1)
    step = chunk_len - overlap
    out = []
    start = 0
    while start < len(seq):
        end = min(start + chunk_len, len(seq))
        out.append(seq[start:end])
        if end >= len(seq):
            break
        start += step
    return out


def to_prost_t5_input(seq: str) -> str:
    return f"<AA2fold> {' '.join(seq)}"


def _env_number(name: str, cast, default=None):
    value = os.environ.get(name)
    if value in (None, ""):
        return default
    try:
        return cast(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid {name}: {value!r}") from exc


def _system_memory() -> tuple[int, int]:
    """Return available and total host RAM without requiring psutil."""
    try:
        values = {}
        with open("/proc/meminfo", "r", encoding="utf-8") as handle:
            for line in handle:
                key, raw = line.split(":", 1)
                values[key] = int(raw.strip().split()[0]) * 1024
        return int(values["MemAvailable"]), int(values["MemTotal"])
    except (OSError, KeyError, ValueError):
        page_size = os.sysconf("SC_PAGE_SIZE")
        available = page_size * os.sysconf("SC_AVPHYS_PAGES")
        total = page_size * os.sysconf("SC_PHYS_PAGES")
        return int(available), int(total)


def _estimated_embedding_bytes(sequence_length: int, target_device: torch.device) -> int:
    """Conservative activation estimate calibrated on the 12 GiB benchmark.

    On an RTX 3060, the measured dynamic cost was about 0.028 GiB/sequence at
    128 aa and 0.138 GiB/sequence at 512 aa. A safety multiplier and a steeper
    curve above 512 aa keep the initial recommendation below the measured OOM
    boundary; runtime OOM backoff remains the final guard.
    """
    length = max(32, int(sequence_length))
    gib_at_128 = 0.0276
    if length <= 512:
        gib = gib_at_128 * (length / 128.0) ** 1.16
    else:
        gib_at_512 = gib_at_128 * 4.0**1.16
        gib = gib_at_512 * (length / 512.0) ** 1.35
    safety_multiplier = 1.25 if target_device.type == "cuda" else 2.5
    return max(1, int(gib * safety_multiplier * 2**30))


def _calibrated_gpu_cap(sequence_length: int, total_bytes: int) -> int:
    """Safe throughput-oriented caps derived from the RTX 3060 benchmark."""
    length = max(1, int(sequence_length))
    if length <= 128:
        reference_cap = 128
    elif length <= 256:
        reference_cap = 64
    elif length <= 512:
        reference_cap = 32
    elif length <= 1024:
        reference_cap = 12
    elif length <= 1536:
        reference_cap = 6
    else:
        reference_cap = 4
    scale = max(0.25, total_bytes / (11.63 * 2**30))
    return max(1, round(reference_cap * scale))


def memory_aware_batch_size(
    sequence_length: int,
    *,
    batch_size: int | None = None,
    max_batch_size: int | None = None,
    memory_fraction: float | None = None,
    reserve_memory_gb: float | None = None,
) -> tuple[int, dict]:
    """Choose a safe initial batch from current free VRAM/RAM."""
    target_device = device
    manual_batch = batch_size if batch_size is not None else _env_number("VYDRA_BATCH_SIZE", int)
    default_cap = 256 if target_device.type == "cuda" else 32
    cap = max_batch_size if max_batch_size is not None else _env_number("VYDRA_MAX_BATCH_SIZE", int, default_cap)
    if manual_batch is not None and max_batch_size is None and "VYDRA_MAX_BATCH_SIZE" not in os.environ:
        cap = max(int(cap), int(manual_batch))
    fraction_default = 0.85 if target_device.type == "cuda" else 0.75
    fraction = memory_fraction if memory_fraction is not None else _env_number(
        "VYDRA_MEMORY_FRACTION", float, fraction_default
    )
    reserve_gb = reserve_memory_gb if reserve_memory_gb is not None else _env_number(
        "VYDRA_RESERVE_MEMORY_GB", float
    )

    if cap is None or cap < 1:
        raise ValueError("max_batch_size must be >= 1")
    if manual_batch is not None and manual_batch < 1:
        raise ValueError("batch_size must be >= 1")
    if not 0.1 <= float(fraction) <= 0.95:
        raise ValueError("memory_fraction must be between 0.10 and 0.95")
    if reserve_gb is not None and reserve_gb < 0:
        raise ValueError("reserve_memory_gb must be >= 0")

    if target_device.type == "cuda":
        free_bytes, total_bytes = torch.cuda.mem_get_info(target_device)
        minimum_reserve = 1.0 * 2**30
    else:
        free_bytes, total_bytes = _system_memory()
        minimum_reserve = 2.0 * 2**30
    reserve_bytes = (
        float(reserve_gb) * 2**30
        if reserve_gb is not None
        else max(minimum_reserve, total_bytes * (1.0 - float(fraction)))
    )
    usable_bytes = max(0, int(free_bytes - reserve_bytes))
    per_sequence_bytes = _estimated_embedding_bytes(sequence_length, target_device)
    automatic = max(1, usable_bytes // per_sequence_bytes)
    calibrated_cap = None
    if target_device.type == "cuda" and manual_batch is None:
        calibrated_cap = _calibrated_gpu_cap(sequence_length, total_bytes)
        automatic = min(automatic, calibrated_cap)
    chosen = min(int(cap), int(manual_batch if manual_batch is not None else automatic))
    return max(1, chosen), {
        "mode": "manual" if manual_batch is not None else "auto",
        "free_gib": free_bytes / 2**30,
        "total_gib": total_bytes / 2**30,
        "reserve_gib": reserve_bytes / 2**30,
        "estimated_gib_per_sequence": per_sequence_bytes / 2**30,
        "calibrated_cap": calibrated_cap,
        "cap": int(cap),
    }


def _embed_items(items: list[dict], tokenizer, model) -> np.ndarray:
    batch_texts = [item["text"] for item in items]
    inputs = tokenizer(batch_texts, add_special_tokens=True, padding=True, return_tensors="pt").to(device)
    with torch.inference_mode():
        if device.type == "cuda":
            with torch.autocast(device_type="cuda", dtype=torch.float16):
                outputs = model(input_ids=inputs["input_ids"], attention_mask=inputs["attention_mask"])
        else:
            outputs = model(input_ids=inputs["input_ids"], attention_mask=inputs["attention_mask"])
        hidden = outputs.last_hidden_state
        mask = inputs["attention_mask"].unsqueeze(-1).expand(hidden.size()).float()
        pooled = (hidden * mask).sum(dim=1) / torch.clamp(mask.sum(dim=1), min=1e-9)
        result = pooled.detach().cpu().float().numpy()
    del inputs, outputs, hidden, mask, pooled
    return result


def _is_memory_error(exc: BaseException) -> bool:
    message = str(exc).lower()
    return isinstance(exc, (torch.cuda.OutOfMemoryError, MemoryError)) or any(
        marker in message
        for marker in ("out of memory", "can't allocate memory", "cannot allocate memory", "defaultcpuallocator")
    )


def embed_records(
    records: list[SequenceRecord],
    progress_callback=None,
    *,
    batch_size: int | None = None,
    max_batch_size: int | None = None,
    memory_fraction: float | None = None,
    reserve_memory_gb: float | None = None,
    length_bin: int | None = None,
) -> np.ndarray:
    with inference_lock:
        try:
            return _embed_records(
                records, progress_callback,
                batch_size=batch_size, max_batch_size=max_batch_size,
                memory_fraction=memory_fraction, reserve_memory_gb=reserve_memory_gb,
                length_bin=length_bin,
            )
        finally:
            release_prost_t5()


def _embed_records(
    records: list[SequenceRecord],
    progress_callback=None,
    *,
    batch_size: int | None = None,
    max_batch_size: int | None = None,
    memory_fraction: float | None = None,
    reserve_memory_gb: float | None = None,
    length_bin: int | None = None,
) -> np.ndarray:
    tokenizer, model = load_prost_t5()
    if not records:
        raise ValueError("No records to embed")
    bin_width = length_bin if length_bin is not None else _env_number("VYDRA_LENGTH_BIN", int, 128)
    if bin_width is None or bin_width < 1:
        raise ValueError("length_bin must be >= 1")
    expanded = []
    chunk_counts = [0 for _ in records]
    for idx, rec in enumerate(records):
        for chunk in chunk_sequence(rec.sequence):
            model_input = to_prost_t5_input(chunk)
            expanded.append({"record_idx": idx, "text": model_input, "length": len(chunk)})
            chunk_counts[idx] += 1

    expanded.sort(key=lambda item: item["length"])
    chunk_vectors = [[] for _ in records]
    processed_chunks = [0 for _ in records]
    processed_records = 0
    cursor = 0

    while cursor < len(expanded):
        first_length = expanded[cursor]["length"]
        bucket_end = cursor
        while bucket_end < len(expanded) and expanded[bucket_end]["length"] <= first_length + bin_width:
            bucket_end += 1
        bucket_length = expanded[bucket_end - 1]["length"]
        recommended, memory_info = memory_aware_batch_size(
            bucket_length,
            batch_size=batch_size,
            max_batch_size=max_batch_size,
            memory_fraction=memory_fraction,
            reserve_memory_gb=reserve_memory_gb,
        )
        active_batch_size = min(recommended, bucket_end - cursor)
        print(
            f"Batch {memory_info['mode']}: len={first_length}-{bucket_length} aa, "
            f"size={active_batch_size}, free={memory_info['free_gib']:.2f} GiB, "
            f"reserve={memory_info['reserve_gib']:.2f} GiB"
        )

        while cursor < bucket_end:
            current_size = min(active_batch_size, bucket_end - cursor)
            items = expanded[cursor : cursor + current_size]
            try:
                pooled_np = _embed_items(items, tokenizer, model)
            except (torch.cuda.OutOfMemoryError, MemoryError, RuntimeError) as exc:
                if not _is_memory_error(exc):
                    raise
                if current_size == 1:
                    raise RuntimeError(
                        f"Insufficient {device.type.upper()} memory even for batch 1 at {bucket_length} aa"
                    ) from exc
                # Break the traceback reference to tensors owned by the failed
                # forward pass before asking the allocator to release its cache.
                exc.__traceback__ = None
                gc.collect()
                if device.type == "cuda":
                    torch.cuda.empty_cache()
                active_batch_size = max(1, current_size // 2)
                print(f"Memory OOM avoided: retrying with batch={active_batch_size}")
                continue

            for item, vector in zip(items, pooled_np):
                record_idx = item["record_idx"]
                chunk_vectors[record_idx].append(vector.astype(np.float32))
                processed_chunks[record_idx] += 1
                if processed_chunks[record_idx] == chunk_counts[record_idx]:
                    processed_records += 1

            if progress_callback:
                progress_callback(processed_records, len(records))

            del pooled_np
            gc.collect()
            if device.type == "cuda":
                torch.cuda.empty_cache()
            cursor += current_size

    per_record = []
    for idx, vectors in enumerate(chunk_vectors):
        chunk_vecs = np.stack(vectors).astype(np.float32)
        merged = chunk_vecs[0] if len(chunk_vecs) == 1 else chunk_vecs.mean(axis=0)
        merged = merged / max(float(np.linalg.norm(merged)), EMB_NORM_EPS)
        per_record.append(merged.astype(np.float32))
    return np.stack(per_record).astype(np.float32)


def normalize_embedding(embedding: np.ndarray) -> np.ndarray:
    emb = np.asarray(embedding, dtype=np.float32).reshape(-1)[:EMB_DIM]
    return (emb / max(float(np.linalg.norm(emb)), EMB_NORM_EPS)).astype(np.float32)


def predict_step(model_name: str, emb: np.ndarray) -> tuple[str, float]:
    loaded_models, loaded_label_classes = load_models()
    model = loaded_models[model_name]
    classes = loaded_label_classes[model_name]
    x = torch.from_numpy(normalize_embedding(emb)).reshape(1, -1).to(device)
    with torch.inference_mode():
        logits = model(x)
        probs = torch.softmax(logits, dim=1)[0]
        conf, idx = torch.max(probs, dim=0)
    return str(classes[int(idx.item())]), float(conf.item())


def empty_annotation() -> dict:
    return {
        "n_sequences": "",
        "metadata_coverage": "",
        "best_taxonomic_level": "",
        "confidence": "",
        "dominant_virus_name": "",
        "virus_name_purity": "",
        "virus_name_coverage": "",
        "dominant_genus": "",
        "genus_purity": "",
        "genus_coverage": "",
        "dominant_family": "",
        "family_purity": "",
        "family_coverage": "",
        "dominant_host": "",
        "host_purity": "",
        "host_coverage": "",
        "representative_seq_id": "",
        "representative_accession": "",
        "representative_product": "",
        "representative_organism": "",
        "representative_virus_name": "",
        "representative_genus": "",
        "representative_family": "",
        "representative_host": "",
        "representative_source_fasta": "",
        "length_known": "",
        "min_length": "",
        "max_length": "",
        "mean_length": "",
        "std_length": "",
        "families_in_cluster": "",
        "genera_in_cluster": "",
        "hosts_in_cluster": "",
        "virus_names_in_cluster": "",
        "products_in_cluster": "",
        "organisms_in_cluster": "",
    }


def get_cluster_annotation(dataset_type: str, class_name: str, cluster_id: int) -> dict:
    if cluster_id < 0:
        return empty_annotation()
    return cluster_annotations.get((dataset_type, class_name, int(cluster_id)), empty_annotation())


def assign_cluster_prototype(emb: np.ndarray, class_name: str, bank: dict[str, dict]) -> tuple[int, float, str]:
    if class_name not in bank:
        return -1, float("nan"), ""
    norm_emb = normalize_embedding(emb)
    distances, indices = gpu_faiss.search_index(bank[class_name]["index"], norm_emb.reshape(1, -1), 1)
    best_idx = int(indices[0, 0])
    if best_idx < 0:
        return -1, float("nan"), ""
    cluster_id = int(bank[class_name]["cluster_ids"][best_idx])
    prototype_seq_id = str(bank[class_name]["seq_ids"][best_idx])
    return cluster_id, float(distances[0, 0]), prototype_seq_id


@serialized_inference
def run_hierarchy(emb: np.ndarray) -> dict:
    release_prost_t5()
    m1, c1 = predict_step("M1_L1_viral_vs_cellular", emb)
    path = [m1]
    confidences = {"M1": c1}
    cluster_id = -1
    cluster_sim = float("nan")
    cluster_branch = ""
    cluster_class = ""
    cluster_dataset_type = ""
    cluster_nearest_seq_id = ""
    cluster_annotation = empty_annotation()
    viral_euk_metadata = empty_viral_euk_class_metadata()

    if m1 == "cellular":
        m2, c2 = predict_step("M2_cellular_3_clases", emb)
        path.append(m2)
        confidences["M2"] = c2
    elif m1 == "viral":
        m3, c3 = predict_step("M3_viral_phage_vs_euk", emb)
        path.append(m3)
        confidences["M3"] = c3
        if m3 == "eukariota":
            m4, c4 = predict_step("M4_viral_euk_978_clases", emb)
            path.append(m4)
            confidences["M4"] = c4
            viral_euk_metadata = get_viral_euk_class_metadata(m4)
        elif m3 == "phage":
            m5, c5 = predict_step("M5_phage_structural_vs_non", emb)
            path.append(m5)
            confidences["M5"] = c5
            if m5 == "structural":
                m6, c6 = predict_step("M6_structural_10_clases", emb)
                path.append(m6)
                confidences["M6"] = c6
                cluster_branch = "structural"
                cluster_dataset_type = "structural"
                cluster_class = m6
                cluster_id, cluster_sim, cluster_nearest_seq_id = assign_cluster_prototype(emb, m6, get_structural_prototype_bank())
            elif m5 == "non_structural":
                cluster_branch = "non_structural"
                cluster_dataset_type = "non_structural"
                cluster_class = "phage_non_struct"
                cluster_id, cluster_sim, cluster_nearest_seq_id = assign_cluster_prototype(
                    emb,
                    "phage_non_struct",
                    get_non_structural_prototype_bank(),
                )

    if cluster_dataset_type and cluster_class:
        cluster_annotation = get_cluster_annotation(cluster_dataset_type, cluster_class, cluster_id)

    return {
        "path": path,
        "path_text": " / ".join(path),
        "confidences": confidences,
        "cluster_branch": cluster_branch,
        "cluster_class": cluster_class,
        "cluster_id": cluster_id,
        "cluster_similarity": cluster_sim,
        "cluster_nearest_seq_id": cluster_nearest_seq_id,
        "cluster_similarity_threshold": thresholds_by_class.get(cluster_class, ""),
        "cluster_annotation": cluster_annotation,
        "cluster_biological_label": biological_label(cluster_annotation),
        "viral_euk_class_metadata": viral_euk_metadata,
    }


def read_file(file_obj) -> str:
    if file_obj is None:
        return ""
    if isinstance(file_obj, Path):
        return file_obj.read_text(encoding="utf-8")
    if isinstance(file_obj, (str, bytes, bytearray)):
        path = Path(file_obj)
        if path.exists():
            return path.read_text(encoding="utf-8")
        return str(file_obj)
    if hasattr(file_obj, "read"):
        data = file_obj.read()
        if isinstance(data, bytes):
            return data.decode("utf-8", errors="replace")
        return str(data)

    path = Path(getattr(file_obj, "path", None) or getattr(file_obj, "name", file_obj))
    if path.exists():
        return path.read_text(encoding="utf-8")
    raise FileNotFoundError(f"Could not resolve input file path from {file_obj!r}")


def load_embedding_file(file_obj) -> tuple[list[SequenceRecord], np.ndarray]:
    path = Path(getattr(file_obj, "name", file_obj))
    suffix = path.suffix.lower()
    data = []
    embeddings = []
    if suffix == ".pt":
        raw = torch.load(path, map_location="cpu", weights_only=False)
        if isinstance(raw, dict) and raw and all(isinstance(v, dict) for v in raw.values()):
            for class_name, seq_map in raw.items():
                for sid, emb in seq_map.items():
                    data.append(SequenceRecord(str(sid), f"Loaded embedding ({class_name})", 0, False))
                    embeddings.append(normalize_embedding(emb))
        elif isinstance(raw, dict):
            for sid, emb in raw.items():
                data.append(SequenceRecord(str(sid), "Loaded embedding", 0, False))
                embeddings.append(normalize_embedding(emb))
        else:
            raise ValueError("Unsupported .pt structure")
    elif suffix == ".npy":
        raw = np.load(path, allow_pickle=True)
        if raw.ndim == 1:
            data.append(SequenceRecord("query_1", "Loaded embedding", 0, False))
            embeddings.append(normalize_embedding(raw))
        elif raw.ndim == 2:
            for idx, emb in enumerate(raw, start=1):
                data.append(SequenceRecord(f"query_{idx}", "Loaded embedding", 0, False))
                embeddings.append(normalize_embedding(emb))
        else:
            raise ValueError("Unsupported .npy shape")
    else:
        raise ValueError("Use .pt or .npy")
    return data, np.stack(embeddings).astype(np.float32)
