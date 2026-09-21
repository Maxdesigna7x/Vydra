from __future__ import annotations

import gc
import json
import os
import threading
from dataclasses import dataclass
from pathlib import Path

os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")

import faiss
import gradio as gr
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from transformers import T5EncoderModel, T5Tokenizer


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
print(f"Starting Vydra inference engine on: {device}")


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


def build_faiss_index(x: np.ndarray) -> faiss.IndexFlatIP:
    index = faiss.IndexFlatIP(x.shape[1])
    index.add(np.ascontiguousarray(x, dtype=np.float32))
    return index


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


def preload_inference_artifacts() -> None:
    load_models()
    load_prost_t5()
    get_structural_prototype_bank()
    get_non_structural_prototype_bank()


def load_prost_t5() -> tuple[T5Tokenizer, T5EncoderModel]:
    global t5_tokenizer, t5_model
    if t5_tokenizer is None or t5_model is None:
        print("Loading Rostlab/ProstT5...")
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
    distances, indices = bank[class_name]["index"].search(norm_emb.reshape(1, -1), 1)
    best_idx = int(indices[0, 0])
    if best_idx < 0:
        return -1, float("nan"), ""
    cluster_id = int(bank[class_name]["cluster_ids"][best_idx])
    prototype_seq_id = str(bank[class_name]["seq_ids"][best_idx])
    return cluster_id, float(distances[0, 0]), prototype_seq_id


def run_hierarchy(emb: np.ndarray) -> dict:
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


NODE_STYLES = {
    "cellular": {"icon": "🔵", "color": "#4A90D9", "label": "Cellular"},
    "viral": {"icon": "🔴", "color": "#E85D5D", "label": "Viral"},
    "bacteria": {"icon": "🦠", "color": "#F5A623", "label": "Bacteria"},
    "eukariota": {"icon": "🟣", "color": "#9B59B6", "label": "Eukariota"},
    "archaea": {"icon": "🟡", "color": "#F1C40F", "label": "Archaea"},
    "phage": {"icon": "🔷", "color": "#1ABC9C", "label": "Phage"},
    "structural": {"icon": "🏗️", "color": "#2ECC71", "label": "Structural"},
    "non_structural": {"icon": "📦", "color": "#95A5A6", "label": "Non-Structural"},
    "non-structural": {"icon": "📦", "color": "#95A5A6", "label": "Non-Structural"},
}


def get_node_style(node: str) -> dict:
    key = node.lower().replace("-", "_").replace(" ", "_")
    return NODE_STYLES.get(key, {"icon": "⬡", "color": "#7F8C8D", "label": node.title()})


def fmt_value(value, digits: int = 3) -> str:
    if value is None or value == "":
        return "N/A"
    try:
        if np.isnan(float(value)):
            return "N/A"
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return str(value)


def fmt_percent(value) -> str:
    if value is None or value == "":
        return "N/A"
    try:
        if np.isnan(float(value)):
            return "N/A"
        return f"{float(value) * 100:.1f}%"
    except (TypeError, ValueError):
        return str(value)


def build_path_html(path_list: list[str], cluster_branch=None, cluster_class=None, cluster_id=None, cluster_sim=None) -> str:
    chips = []
    for i, node in enumerate(path_list):
        style = get_node_style(node)
        chips.append(
            f"<span class='path-chip' style='--chip-color:{style['color']}'>"
            f"<span class='chip-icon'>{style['icon']}</span>{style['label']}"
            f"</span>"
        )
        if i < len(path_list) - 1:
            chips.append("<span class='path-arrow'>→</span>")

    cluster_html = ""
    if cluster_branch:
        cluster_html = (
            f"<div class='cluster-pill'>🧩 Cluster {cluster_id} · {cluster_branch} / {cluster_class} · sim {cluster_sim:.4f}</div>"
        )

    return f"<div class='path-wrap'>{''.join(chips)}</div>{cluster_html}"


def build_cluster_biology_html(row: dict) -> str:
    if not row.get("cluster_branch"):
        return ""
    ann = row.get("cluster_annotation", {}) or {}
    label = row.get("cluster_biological_label") or "unannotated"
    return f"""
    <div class='bio-panel'>
      <div class='bio-title'>🧬 Biological cluster context</div>
      <div class='bio-grid'>
        <div><span>Label</span><b>{label}</b></div>
        <div><span>Level</span><b>{ann.get('best_taxonomic_level') or 'N/A'}</b></div>
        <div><span>Confidence</span><b>{ann.get('confidence') or 'N/A'}</b></div>
        <div><span>Cluster size</span><b>{ann.get('n_sequences') or 'N/A'}</b></div>
        <div><span>Threshold</span><b>{fmt_value(row.get('cluster_similarity_threshold'))}</b></div>
        <div><span>Prototype similarity</span><b>{fmt_value(row.get('cluster_similarity'))}</b></div>
      </div>
      <div class='bio-line'><b>Nearest prototype:</b> {row.get('cluster_nearest_seq_id') or 'N/A'}</div>
      <div class='bio-line'><b>Representative sequence:</b> {ann.get('representative_seq_id') or 'N/A'} · {ann.get('representative_product') or 'N/A'}</div>
      <div class='bio-line'><b>Dominant family:</b> {ann.get('dominant_family') or 'N/A'} · purity {fmt_percent(ann.get('family_purity'))} · coverage {fmt_percent(ann.get('family_coverage'))}</div>
      <div class='bio-line'><b>Dominant genus:</b> {ann.get('dominant_genus') or 'N/A'} · purity {fmt_percent(ann.get('genus_purity'))} · coverage {fmt_percent(ann.get('genus_coverage'))}</div>
      <div class='bio-line'><b>Dominant host:</b> {ann.get('dominant_host') or 'N/A'} · purity {fmt_percent(ann.get('host_purity'))} · coverage {fmt_percent(ann.get('host_coverage'))}</div>
      <div class='bio-line'><b>Length:</b> min {fmt_value(ann.get('min_length'), 0)} aa · max {fmt_value(ann.get('max_length'), 0)} aa · mean {fmt_value(ann.get('mean_length'))} aa</div>
      <div class='bio-line'><b>Families in cluster:</b> {ann.get('families_in_cluster') or 'N/A'}</div>
      <div class='bio-line'><b>Genera in cluster:</b> {ann.get('genera_in_cluster') or 'N/A'}</div>
      <div class='bio-line'><b>Products in cluster:</b> {ann.get('products_in_cluster') or 'N/A'}</div>
      <div class='bio-line muted'><b>Interpretation:</b> use this as cluster-level context, not as direct taxonomic classification of the query.</div>
    </div>
    """


def build_viral_euk_class_html(row: dict) -> str:
    meta = row.get("viral_euk_class_metadata", {}) or {}
    if not meta.get("class_number"):
        return ""
    return f"""
    <div class='bio-panel'>
      <div class='bio-title'>🧬 VirDetect-AI class context</div>
      <div class='bio-grid'>
        <div><span>Class</span><b>{meta.get('class_number') or 'N/A'}</b></div>
        <div><span>Representative</span><b>{meta.get('cluster_rep_sequence_accession') or 'N/A'}</b></div>
        <div><span>Family 2023</span><b>{meta.get('family_label_ncbi_2023') or 'N/A'}</b></div>
        <div><span>Protein function</span><b>{meta.get('protein_function_class') or 'N/A'}</b></div>
        <div><span>Host</span><b>{meta.get('host') or 'N/A'}</b></div>
        <div><span>Molecule type</span><b>{meta.get('molecule_type') or 'N/A'}</b></div>
      </div>
      <div class='bio-line'><b>Protein description:</b> {meta.get('protein_description') or 'N/A'}</div>
      <div class='bio-line'><b>Genus:</b> {meta.get('genus') or 'N/A'}</div>
      <div class='bio-line'><b>Families in class (2021):</b> {meta.get('families_in_class_2021') or 'N/A'}</div>
      <div class='bio-line'><b>Sequences:</b> {fmt_value(meta.get('sequences_per_class'), 0)} · {fmt_value(meta.get('sequences_percent'))}% of class table</div>
      <div class='bio-line'><b>Length:</b> max {fmt_value(meta.get('max_length'), 0)} aa · mean {fmt_value(meta.get('mean_length'))} aa · std {fmt_value(meta.get('std_length'))}</div>
      <div class='bio-line'><b>k-mers:</b> {fmt_value(meta.get('kmers_per_class'), 0)} · {fmt_value(meta.get('kmers_percent'))}%</div>
      <div class='bio-line muted'><b>Source:</b> VirDetect-AI Supplementary Table S1, official class dictionary.</div>
    </div>
    """


def build_result_card_html(row: dict) -> str:
    final_style = get_node_style(row["path"][-1])
    conf = " · ".join(f"{k}: {v:.3f}" for k, v in row["confidences"].items()) or "N/A"
    preview = row["sequence"][:96]
    if len(row["sequence"]) > 96:
        preview += "..."
    return f"""
    <div class='result-card' style='--accent:{final_style['color']}'>
      <div class='result-head'>
        <div>
          <div class='result-label'>Sequence ID</div>
          <div class='result-id'>{row['seq_id']}</div>
        </div>
        <div class='result-badge'>{final_style['icon']} {final_style['label']}</div>
      </div>
      <div class='result-body'>
        {build_path_html(row['path'], row['cluster_branch'], row['cluster_class'], row['cluster_id'], row['cluster_similarity'])}
        {build_viral_euk_class_html(row)}
        {build_cluster_biology_html(row)}
        <div class='meta-line'><b>Path:</b> {row['path_text']}</div>
        <div class='meta-line'><b>Confidence:</b> {conf}</div>
        <div class='preview-box'>{preview}</div>
      </div>
    </div>
    """


def results_to_html(rows: list[dict]) -> str:
    cards = [build_result_card_html(row) for row in rows[:5]]
    extra = "" if len(rows) <= 5 else f"<div class='results-note'>+{len(rows) - 5} additional records in the downloadable report</div>"
    return (
        f"<div class='results-shell'>"
        f"<div class='results-summary'>{len(rows)} sequence{'s' if len(rows) != 1 else ''} processed · showing {min(len(rows), 5)} of {len(rows)}</div>"
        + "".join(cards)
        + extra
        + "</div>"
    )


def write_report(rows: list[dict]) -> str:
    out_path = BASE_DIR / "vydra_predictions.txt"
    with out_path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(f"ID: {row['seq_id']}\n")
            handle.write(f"Path: {row['path_text']}\n")
            handle.write(f"Confidence: {row['confidences']}\n")
            handle.write(f"Cluster branch: {row['cluster_branch']}\n")
            handle.write(f"Cluster class: {row['cluster_class']}\n")
            handle.write(f"Cluster id: {row['cluster_id']}\n")
            handle.write(f"Cluster similarity: {row['cluster_similarity']}\n")
            handle.write(f"Cluster nearest prototype: {row.get('cluster_nearest_seq_id', '')}\n")
            handle.write(f"Cluster similarity threshold: {row.get('cluster_similarity_threshold', '')}\n")
            handle.write(f"Cluster biological label: {row.get('cluster_biological_label', '')}\n")
            vmeta = row.get("viral_euk_class_metadata", {}) or {}
            handle.write(f"Viral_Euk class number: {vmeta.get('class_number', '')}\n")
            handle.write(f"Viral_Euk representative accession: {vmeta.get('cluster_rep_sequence_accession', '')}\n")
            handle.write(f"Viral_Euk family NCBI 2023: {vmeta.get('family_label_ncbi_2023', '')}\n")
            handle.write(f"Viral_Euk families in class 2021: {vmeta.get('families_in_class_2021', '')}\n")
            handle.write(f"Viral_Euk protein description: {vmeta.get('protein_description', '')}\n")
            handle.write(f"Viral_Euk protein function class: {vmeta.get('protein_function_class', '')}\n")
            handle.write(f"Viral_Euk host: {vmeta.get('host', '')}\n")
            handle.write(f"Viral_Euk molecule type: {vmeta.get('molecule_type', '')}\n")
            handle.write(f"Viral_Euk genus: {vmeta.get('genus', '')}\n")
            ann = row.get("cluster_annotation", {}) or {}
            handle.write(f"Cluster taxonomic level: {ann.get('best_taxonomic_level', '')}\n")
            handle.write(f"Cluster annotation confidence: {ann.get('confidence', '')}\n")
            handle.write(f"Cluster size: {ann.get('n_sequences', '')}\n")
            handle.write(f"Cluster metadata coverage: {ann.get('metadata_coverage', '')}\n")
            handle.write(f"Cluster representative seq_id: {ann.get('representative_seq_id', '')}\n")
            handle.write(f"Cluster representative accession: {ann.get('representative_accession', '')}\n")
            handle.write(f"Cluster representative product: {ann.get('representative_product', '')}\n")
            handle.write(f"Cluster representative organism: {ann.get('representative_organism', '')}\n")
            handle.write(f"Cluster min length: {ann.get('min_length', '')}\n")
            handle.write(f"Cluster max length: {ann.get('max_length', '')}\n")
            handle.write(f"Cluster mean length: {ann.get('mean_length', '')}\n")
            handle.write(f"Cluster std length: {ann.get('std_length', '')}\n")
            handle.write(f"Dominant family: {ann.get('dominant_family', '')}\n")
            handle.write(f"Family purity: {ann.get('family_purity', '')}\n")
            handle.write(f"Family coverage: {ann.get('family_coverage', '')}\n")
            handle.write(f"Dominant genus: {ann.get('dominant_genus', '')}\n")
            handle.write(f"Genus purity: {ann.get('genus_purity', '')}\n")
            handle.write(f"Genus coverage: {ann.get('genus_coverage', '')}\n")
            handle.write(f"Dominant host: {ann.get('dominant_host', '')}\n")
            handle.write(f"Host purity: {ann.get('host_purity', '')}\n")
            handle.write(f"Host coverage: {ann.get('host_coverage', '')}\n")
            handle.write(f"Families in cluster: {ann.get('families_in_cluster', '')}\n")
            handle.write(f"Genera in cluster: {ann.get('genera_in_cluster', '')}\n")
            handle.write(f"Hosts in cluster: {ann.get('hosts_in_cluster', '')}\n")
            handle.write(f"Products in cluster: {ann.get('products_in_cluster', '')}\n")
            handle.write(f"Sequence: {row['sequence']}\n")
            handle.write("-" * 80 + "\n")
    return str(out_path)


def predict_records(records: list[SequenceRecord], embeddings: np.ndarray) -> tuple[str, str]:
    rows = []
    for rec, emb in zip(records, embeddings):
        pred = run_hierarchy(emb)
        rows.append({"seq_id": rec.seq_id, "sequence": rec.sequence, **pred})
    return results_to_html(rows), write_report(rows)


def predict_from_text(sequence_or_fasta: str):
    records = parse_fasta_text(sequence_or_fasta or "")
    if not records:
        return "<div class='empty-state'>No valid sequence found.</div>", None
    embeddings = embed_records(records)
    html, report = predict_records(records, embeddings)
    return html, report


def predict_from_fasta(file_obj):
    text = read_file(file_obj)
    return predict_from_text(text)


def predict_from_embedding(file_obj):
    if file_obj is None:
        return "<div class='empty-state'>Upload a <code>.pt</code> or <code>.npy</code> file.</div>", None
    try:
        records, embeddings = load_embedding_file(file_obj)
        html, report = predict_records(records, embeddings)
        return html, report
    except Exception as exc:
        return f"<div class='empty-state'>{exc}</div>", None


CSS = """
.gradio-container {
    background: #0d0d1a !important;
    color: #e0e0ff !important;
    font-family: 'JetBrains Mono', 'Fira Code', monospace !important;
    max-width: 1180px !important;
    margin: 0 auto !important;
}
.gradio-container h1, .gradio-container h2, .gradio-container h3 { color: #e0e0ff !important; }
.links-bar a {
    color: #4A90D9;
    text-decoration: none;
    border: 1px solid #4A90D9;
    border-radius: 20px;
    padding: 4px 14px;
    font-size: 0.82em;
    transition: all 0.2s ease;
    margin-right: 8px;
}
.links-bar a:hover { background: #4A90D922; }
.compact-upload .wrap { min-height: 78px !important; padding: 8px !important; }
.compact-upload textarea { min-height: 148px !important; max-height: 148px !important; }
.compact-upload .upload-container,
.compact-upload .upload-drop-area,
.compact-upload .upload-area { min-height: 148px !important; max-height: 148px !important; height: 148px !important; }
.section-label p { margin: 0 0 6px 0 !important; }
.result-card {
    background: #1a1a2e;
    border: 1.5px solid #2a2a4a;
    border-left: 4px solid var(--accent);
    border-radius: 14px;
    padding: 16px 18px;
    margin-bottom: 12px;
    box-shadow: 0 0 18px rgba(0,0,0,0.16);
}
.result-head { display: flex; justify-content: space-between; gap: 12px; align-items: flex-start; margin-bottom: 10px; }
.result-label { color: #8e8ea8; font-size: 0.72em; text-transform: uppercase; letter-spacing: 0.08em; }
.result-id { color: #e0e0ff; font-weight: 800; font-size: 0.96em; word-break: break-word; }
.result-badge {
    background: color-mix(in srgb, var(--accent) 18%, transparent);
    border: 1px solid var(--accent);
    color: var(--accent);
    border-radius: 20px;
    padding: 3px 12px;
    font-size: 0.75em;
    font-weight: 700;
    white-space: nowrap;
}
.path-wrap { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; margin-bottom: 10px; }
.path-chip {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    border: 1px solid var(--chip-color);
    color: var(--chip-color);
    background: color-mix(in srgb, var(--chip-color) 12%, transparent);
    border-radius: 999px;
    padding: 5px 10px;
    font-size: 0.78em;
    font-weight: 700;
}
.chip-icon { font-size: 1.05em; }
.path-arrow { color: #6f6f8c; font-weight: 700; }
.cluster-pill {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 10px;
    background: #1abc9c22;
    border: 1px solid #1abc9c;
    border-radius: 20px;
    padding: 5px 12px;
    color: #1abc9c;
    font-size: 0.8em;
    font-weight: 700;
    flex-wrap: wrap;
}
.meta-line { color: #d6d6ef; font-size: 0.84em; margin-top: 4px; word-break: break-word; }
.bio-panel {
    background: #101023;
    border: 1px solid #2f3f5f;
    border-radius: 12px;
    padding: 10px 12px;
    margin: 8px 0 10px 0;
}
.bio-title { color: #8ee6d1; font-weight: 800; font-size: 0.82em; margin-bottom: 8px; }
.bio-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); gap: 8px; margin-bottom: 8px; }
.bio-grid div { background: #17172d; border: 1px solid #29294a; border-radius: 9px; padding: 7px 8px; }
.bio-grid span { display:block; color:#8e8ea8; font-size:0.68em; text-transform:uppercase; letter-spacing:0.06em; }
.bio-grid b { color:#e0e0ff; font-size:0.82em; overflow-wrap:anywhere; }
.bio-line { color:#cfcfeb; font-size:0.78em; margin-top:4px; overflow-wrap:anywhere; }
.bio-line.muted { color:#8f8fa8; font-style:italic; }
.preview-box {
    margin-top: 10px;
    background: #0d0d1a;
    border: 1px solid #24243b;
    border-radius: 10px;
    padding: 8px 10px;
    color: #9393ad;
    font-size: 0.78em;
    overflow-wrap: anywhere;
}
.results-shell { display: flex; flex-direction: column; gap: 10px; }
.results-summary { color: #aaaac7; font-size: 0.8em; margin-bottom: 4px; padding-bottom: 8px; border-bottom: 1px solid #22223b; }
.results-note { text-align: center; color: #8f8fa8; font-size: 0.82em; padding: 10px; border: 1px dashed #333; border-radius: 10px; }
.empty-state { color: #e85d5d; font-weight: 700; text-align: center; padding: 18px; border: 1px dashed #333; border-radius: 12px; }
.empty-state code { color: #e0e0ff; }
.progress-box { display:flex; align-items:center; gap:10px; color:#aaa; font-size:0.85em; padding:10px 12px; border:1px dashed #333; border-radius:10px; }
.spinner { width:16px; height:16px; border-radius:50%; border:2px solid #555; border-top-color:#E85D5D; animation:spin 0.9s linear infinite; }
@keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
"""


with gr.Blocks(
    title="Vydra Protein Classifier",
    css=CSS,
    theme=gr.themes.Base(primary_hue="red", secondary_hue="teal", neutral_hue="slate").set(
        body_background_fill="#0d0d1a",
        body_text_color="#e0e0ff",
        block_background_fill="#14142a",
        block_border_color="#2a2a4a",
        input_background_fill="#1a1a2e",
    ),
) as demo:
    gr.HTML(
        """
        <div style="text-align:center; padding:20px 0 10px 0;">
          <h1 style="font-size:1.7em; margin:0; background: linear-gradient(90deg,#E85D5D,#9B59B6,#4A90D9); -webkit-background-clip:text; -webkit-text-fill-color:transparent; font-weight:800;">
            Vydra Protein Classifier
          </h1>
          <p style="color:#888; font-size:0.85em; margin-top:6px;">Hierarchical protein classification with ProstT5 embeddings and a cascade of MLP heads</p>
        </div>
        """
    )

    gr.HTML(
        """
        <div class="links-bar" style="display:flex; justify-content:center; gap:8px; margin-bottom:16px; flex-wrap:wrap;">
          <a href="https://github.com/" target="_blank">GitHub</a>
          <a href="https://huggingface.co/spaces" target="_blank">HF Spaces</a>
        </div>
        """
    )

    with gr.Accordion("📌 View hierarchical tree", open=False):
        gr.HTML(
            """
            <div style="display:flex; justify-content:center; padding:10px 0;">
              <svg viewBox="0 0 700 340" width="100%" style="max-width:680px; font-family:monospace;">
                <rect x="295" y="10" width="110" height="36" rx="10" fill="#1a1a3a" stroke="#4A90D9" stroke-width="1.5"/>
                <text x="350" y="33" text-anchor="middle" fill="#e0e0ff" font-size="12" font-weight="bold">Protein</text>
                <line x1="350" y1="46" x2="160" y2="90" stroke="#4A90D966" stroke-width="1.5"/>
                <line x1="350" y1="46" x2="540" y2="90" stroke="#E85D5D66" stroke-width="1.5"/>
                <rect x="100" y="90" width="120" height="36" rx="10" fill="#1a1a3a" stroke="#4A90D9" stroke-width="1.5"/>
                <text x="160" y="113" text-anchor="middle" fill="#4A90D9" font-size="12" font-weight="bold">🔵 Cellular</text>
                <rect x="480" y="90" width="120" height="36" rx="10" fill="#1a1a3a" stroke="#E85D5D" stroke-width="1.5"/>
                <text x="540" y="113" text-anchor="middle" fill="#E85D5D" font-size="12" font-weight="bold">🔴 Viral</text>
                <line x1="160" y1="126" x2="60" y2="180" stroke="#F5A62366" stroke-width="1.2"/>
                <line x1="160" y1="126" x2="160" y2="180" stroke="#9B59B666" stroke-width="1.2"/>
                <line x1="160" y1="126" x2="265" y2="180" stroke="#F1C40F66" stroke-width="1.2"/>
                <rect x="10" y="180" width="100" height="34" rx="9" fill="#1a1a3a" stroke="#F5A623" stroke-width="1.2"/>
                <text x="60" y="202" text-anchor="middle" fill="#F5A623" font-size="11">🦠 Bacteria</text>
                <rect x="115" y="180" width="100" height="34" rx="9" fill="#1a1a3a" stroke="#9B59B6" stroke-width="1.2"/>
                <text x="165" y="202" text-anchor="middle" fill="#9B59B6" font-size="11">🟣 Eukariota</text>
                <rect x="220" y="180" width="100" height="34" rx="9" fill="#1a1a3a" stroke="#F1C40F" stroke-width="1.2"/>
                <text x="270" y="202" text-anchor="middle" fill="#F1C40F" font-size="11">🟡 Archaea</text>
                <line x1="540" y1="126" x2="460" y2="180" stroke="#9B59B666" stroke-width="1.2"/>
                <line x1="540" y1="126" x2="620" y2="180" stroke="#1ABC9C66" stroke-width="1.2"/>
                <rect x="405" y="180" width="110" height="34" rx="9" fill="#1a1a3a" stroke="#9B59B6" stroke-width="1.2"/>
                <text x="460" y="197" text-anchor="middle" fill="#9B59B6" font-size="10">🟣 Eukariota</text>
                <text x="460" y="210" text-anchor="middle" fill="#9B59B6" font-size="9">(980 classes)</text>
                <rect x="565" y="180" width="110" height="34" rx="9" fill="#1a1a3a" stroke="#1ABC9C" stroke-width="1.2"/>
                <text x="620" y="202" text-anchor="middle" fill="#1ABC9C" font-size="11">🔷 Phage</text>
                <line x1="620" y1="214" x2="490" y2="260" stroke="#2ECC7166" stroke-width="1.2"/>
                <line x1="620" y1="214" x2="625" y2="260" stroke="#95A5A666" stroke-width="1.2"/>
                <rect x="435" y="260" width="105" height="34" rx="9" fill="#1a1a3a" stroke="#2ECC71" stroke-width="1.2"/>
                <text x="490" y="277" text-anchor="middle" fill="#2ECC71" font-size="10">🏗 Structural</text>
                <text x="490" y="290" text-anchor="middle" fill="#2ECC71" font-size="9">(10 classes)</text>
                <rect x="572" y="260" width="105" height="34" rx="9" fill="#1a1a3a" stroke="#95A5A6" stroke-width="1.2"/>
                <text x="625" y="274" text-anchor="middle" fill="#95A5A6" font-size="9">📦 Non</text>
                <text x="625" y="287" text-anchor="middle" fill="#95A5A6" font-size="9">Struct.</text>
              </svg>
            </div>
            """
        )

    gr.HTML("<div style='height:4px;'></div>")

    with gr.Row(equal_height=True):
        with gr.Column(scale=1, elem_classes="compact-upload"):
            gr.Markdown("**✍️ Option 1 · Sequence / FASTA text**", elem_classes="section-label")
            seq_text = gr.Textbox(
                label="Paste protein sequence or FASTA",
                lines=8,
                placeholder=">query_1\nMSTNPKPQR...",
            )
            btn_text = gr.Button("🧬 Run text prediction", variant="primary", size="sm")

        with gr.Column(scale=1, elem_classes="compact-upload"):
            gr.Markdown("**📥 Option 2 · FASTA file**", elem_classes="section-label")
            fasta_file = gr.File(label="Upload .fasta / .fa / .txt", file_types=[".fasta", ".fa", ".txt"], height=150)
            btn_fasta = gr.Button("🧬 Run FASTA prediction", variant="primary", size="sm")

        with gr.Column(scale=1, elem_classes="compact-upload"):
            gr.Markdown("**📥 Option 3 · Embeddings (.pt / .npy)**", elem_classes="section-label")
            emb_file = gr.File(label="Upload .pt or .npy", file_types=[".pt", ".npy"], height=150)
            btn_emb = gr.Button("⚗️ Run embedding prediction", variant="secondary", size="sm")

    progress_box = gr.HTML(
        """
        <div class="progress-box" style="margin-top:8px; margin-bottom:10px;" >
          <div class="spinner"></div>
          Processing...
        </div>
        """,
        visible=False,
    )

    gr.Markdown("### 📊 Results")
    out_html = gr.HTML("<div class='empty-state'>Results will appear here.</div>")
    with gr.Column(visible=False) as download_box:
        out_file = gr.File(label="Download full report", visible=False)

    def run_text_and_show(text):
        html, filepath = predict_from_text(text)
        visible = filepath is not None
        return html, gr.update(value=filepath, visible=visible), gr.update(visible=visible)

    def run_fasta_and_show(file_obj):
        html, filepath = predict_from_fasta(file_obj)
        visible = filepath is not None
        return html, gr.update(value=filepath, visible=visible), gr.update(visible=visible)

    def run_emb_and_show(file_obj):
        html, filepath = predict_from_embedding(file_obj)
        visible = filepath is not None
        return html, gr.update(value=filepath, visible=visible), gr.update(visible=visible)

    btn_text.click(
        fn=lambda: gr.update(visible=True),
        outputs=progress_box,
        show_progress="hidden",
    ).then(
        fn=run_text_and_show,
        inputs=seq_text,
        outputs=[out_html, out_file, download_box],
        show_progress="hidden",
    ).then(
        fn=lambda: gr.update(visible=False),
        outputs=progress_box,
        show_progress="hidden",
    )

    btn_fasta.click(
        fn=lambda: gr.update(visible=True),
        outputs=progress_box,
        show_progress="hidden",
    ).then(
        fn=run_fasta_and_show,
        inputs=fasta_file,
        outputs=[out_html, out_file, download_box],
        show_progress="hidden",
    ).then(
        fn=lambda: gr.update(visible=False),
        outputs=progress_box,
        show_progress="hidden",
    )

    btn_emb.click(
        fn=lambda: gr.update(visible=True),
        outputs=progress_box,
        show_progress="hidden",
    ).then(
        fn=run_emb_and_show,
        inputs=emb_file,
        outputs=[out_html, out_file, download_box],
        show_progress="hidden",
    ).then(
        fn=lambda: gr.update(visible=False),
        outputs=progress_box,
        show_progress="hidden",
    )

    gr.HTML("<div style='text-align:center; color:#444; font-size:0.75em; margin-top:20px;'>Built with Gradio · ProstT5 · PyTorch</div>")


if __name__ == "__main__":
    demo.launch()
