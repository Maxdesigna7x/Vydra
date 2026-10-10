#!/usr/bin/env python3
"""Run Vydra on protein FASTA files under a directory and retain source paths.

FASTA files are discovered recursively and nucleotide or ambiguous records
are excluded by content, independently of their extension. Input records are assigned stable IDs and sorted by
length before Vydra runs. A single terminal '*' stop marker is removed from the
model input while the original header and length remain in the manifest.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import shlex
import statistics
import subprocess
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
AA_ALLOWED = set("ACDEFGHIKLMNPQRSTVWYBXZUOJ*")
DNA_IUPAC = set("ACGTUNRYKMSWBDHV")
INPUT_EXTENSIONS = {".faa", ".fasta", ".fa", ".fas", ".fna", ".ffn"}
MODEL_REPO = "Rostlab/ProstT5_fp16"
MODEL_REVISION = "07a6547d51de603f1be84fd9f2db4680ee535a86"


def resolve_model_path(explicit: Path | None, offline: bool, language='en') -> Path:
    configured = explicit or os.environ.get("VYDRA_PROSTT5_PATH")
    if configured:
        path = Path(configured).expanduser().resolve()
        if not path.is_dir():
            raise FileNotFoundError(f"No existe el snapshot local del modelo: {path}")
        return path
    from huggingface_hub import snapshot_download
    options = dict(repo_id=MODEL_REPO, revision=MODEL_REVISION,
                   allow_patterns=["*.json", "*.model", "*.bin", "*.safetensors"])
    try:
        cached = Path(snapshot_download(**options, local_files_only=True))
        weights = list(cached.glob("*.safetensors")) + list(cached.glob("pytorch_model*.bin"))
        if (cached / "config.json").is_file() and (cached / "spiece.model").is_file() and weights and all(p.is_file() and p.stat().st_size > 0 for p in weights):
            indices = list(cached.glob("*.index.json"))
            shards = {name for index in indices for name in json.loads(index.read_text()).get("weight_map", {}).values()}
            if all((cached / shard).is_file() for shard in shards):
                return cached
        if offline:
            raise FileNotFoundError("La caché de ProstT5 está incompleta; ejecuta sin --offline para descargar los archivos faltantes")
    except FileNotFoundError:
        if offline:
            raise
    except Exception as exc:
        from huggingface_hub.errors import LocalEntryNotFoundError
        if not isinstance(exc, LocalEntryNotFoundError) or offline:
            raise
    print(f"Downloading {MODEL_REPO} to the Hugging Face cache..." if language == 'en' else f"Descargando {MODEL_REPO} a la caché de Hugging Face...", flush=True)
    return Path(snapshot_download(**options))


def parse_fasta(path: Path):
    header: str | None = None
    pieces: list[str] = []
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for raw in handle:
            line = raw.strip()
            if not line:
                continue
            if line.startswith(">"):
                if header is not None:
                    yield header, "".join(pieces)
                header = line[1:].strip()
                pieces = []
            elif header is None:
                raise ValueError(f"Secuencia antes del primer encabezado FASTA en {path}")
            else:
                pieces.append("".join(line.split()))
    if header is not None:
        yield header, "".join(pieces)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, payload: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def prepare_inputs(input_root: Path, output_root: Path, input_files=None) -> tuple[Path, Path, list[dict[str, Any]], dict[str, Any]]:
    files = sorted(input_files) if input_files is not None else sorted(p for p in input_root.rglob("*") if p.is_file() and p.suffix.lower() in INPUT_EXTENSIONS)
    if not files:
        raise FileNotFoundError(f"No se encontraron archivos FASTA bajo {input_root}")

    all_records: list[tuple[int, int, str, str, dict[str, Any]]] = []
    manifest: list[dict[str, Any]] = []
    file_hashes: dict[str, str] = {}
    terminal_stops = 0
    total_original_residues = 0
    total_model_residues = 0
    sequence_count = 0
    long_records = 0
    embedding_windows = 0

    excluded_path = output_root / "secuencias_excluidas.csv"
    excluded_counts: Counter[str] = Counter()
    excluded_handle = excluded_path.open("w", encoding="utf-8", newline="")
    excluded_writer = csv.DictWriter(excluded_handle, fieldnames=["source_relative_path", "source_folder", "source_file", "record_number", "original_header", "sequence_length", "reason"])
    excluded_writer.writeheader()

    for file_number, path in enumerate(files, start=1):
        relative_path = path.relative_to(input_root).as_posix()
        source_folder = path.parent.relative_to(input_root).as_posix()
        if source_folder == ".":
            source_folder = ""
        checksum = sha256_file(path)
        file_hashes[relative_path] = checksum
        for record_number, (header, raw_sequence) in enumerate(parse_fasta(path), start=1):
            sequence = raw_sequence.upper()
            original_length = len(sequence)
            stop_removed = sequence.endswith("*")
            if stop_removed:
                sequence = sequence[:-1]
            letters = set(sequence)
            reason = None
            if not sequence:
                reason = "empty_sequence"
            elif letters - AA_ALLOWED:
                reason = "invalid_protein_symbols"
            elif letters.issubset(DNA_IUPAC):
                reason = "nucleotide_or_ambiguous_alphabet"
            if reason:
                excluded_counts[reason] += 1
                excluded_writer.writerow({"source_relative_path": relative_path,
                    "source_folder": source_folder, "source_file": path.name,
                    "record_number": record_number, "original_header": header,
                    "sequence_length": original_length, "reason": reason})
                continue
            if stop_removed:
                terminal_stops += 1
            alphabet_note = "protein_likely"

            seq_id = f"F{file_number:03d}_R{record_number:07d}"
            row = {
                "seq_id": seq_id,
                "source_path": str(path.resolve()),
                "source_relative_path": relative_path,
                "source_folder": source_folder,
                "source_file": path.name,
                "original_id": header.split()[0] if header.split() else seq_id,
                "original_header": header,
                "original_length_aa": original_length,
                "model_input_length_aa": len(sequence),
                "terminal_stop_removed": stop_removed,
                "alphabet_note": alphabet_note,
                "source_file_sha256": checksum,
            }
            all_records.append((len(sequence), file_number, record_number, sequence, row))
            manifest.append(row)
            sequence_count += 1
            total_original_residues += original_length
            total_model_residues += len(sequence)
            if len(sequence) > 2048:
                long_records += 1
                chunk_count = 1
                start = 1536
                while start < len(sequence):
                    end = min(start + 2048, len(sequence))
                    chunk_count += 1
                    if end >= len(sequence):
                        break
                    start += 1536
                embedding_windows += chunk_count
            else:
                embedding_windows += 1
    excluded_handle.close()
    if not manifest:
        raise ValueError(f"No se encontraron proteínas identificables; consulta {excluded_path}")

    all_records.sort(key=lambda item: (item[0], item[1], item[2]))
    combined_path = output_root / "input_proteinas_ordenadas.faa"
    manifest_path = output_root / "manifest_secuencias.csv"
    with combined_path.open("w", encoding="utf-8") as fasta:
        for _, _, _, sequence, row in all_records:
            fasta.write(f">{row['seq_id']}\n")
            for offset in range(0, len(sequence), 80):
                fasta.write(sequence[offset : offset + 80] + "\n")
    manifest_fields = list(manifest[0])
    with manifest_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=manifest_fields)
        writer.writeheader()
        writer.writerows(manifest)

    preparation = {
        "input_files": len(files),
        "excluded_sequences": sum(excluded_counts.values()),
        "excluded_by_reason": dict(excluded_counts),
        "sequence_detection_policy": "exclude invalid symbols and nucleotide/ambiguous IUPAC alphabets regardless of file extension",
        "input_sequences": sequence_count,
        "total_original_amino_acids": total_original_residues,
        "total_amino_acids_sent_to_model": total_model_residues,
        "sequences_over_2048_aa": long_records,
        "prostt5_embedding_windows": embedding_windows,
        "terminal_stop_markers_removed": terminal_stops,
        "ambiguous_alphabet_records_kept": 0,
        "records_with_unusual_symbols_kept": 0,
        "source_file_sha256": file_hashes,
    }
    all_records.clear()
    return combined_path, manifest_path, manifest, preparation


def json_safe(value: Any) -> Any:
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(v) for v in value]
    return value


def flatten(value: Any, prefix: str = "", output: dict[str, Any] | None = None) -> dict[str, Any]:
    if output is None:
        output = {}
    if isinstance(value, dict):
        for key, nested in value.items():
            flatten(nested, f"{prefix}.{key}" if prefix else str(key), output)
    elif isinstance(value, list):
        output[prefix] = "/".join(str(v) for v in value)
    else:
        output[prefix] = value
    return output


def new_stats() -> dict[str, Any]:
    return {
        "sequences": 0,
        "cellular": 0,
        "viral": 0,
        "cellular_bacteria": 0,
        "cellular_archaea": 0,
        "cellular_eukaryota": 0,
        "viral_phage": 0,
        "viral_eukaryota": 0,
        "phage_structural": 0,
        "phage_non_structural": 0,
        "cluster_assigned": 0,
        "chunked": 0,
        "sum_original_length_aa": 0,
        "max_original_length_aa": 0,
        "sum_confidence_M1": 0.0,
    }


def add_result(stats: dict[str, Any], row: dict[str, Any]) -> None:
    stats["sequences"] += 1
    stats["chunked"] += int(bool(row.get("chunked")))
    length = int(row.get("original_length_aa", row.get("length", 0)))
    stats["sum_original_length_aa"] += length
    stats["max_original_length_aa"] = max(stats["max_original_length_aa"], length)
    path = row.get("path", [])
    if path and path[0] == "cellular":
        stats["cellular"] += 1
        if len(path) > 1 and path[1] == "bacteria":
            stats["cellular_bacteria"] += 1
        elif len(path) > 1 and path[1] == "archaea":
            stats["cellular_archaea"] += 1
        elif len(path) > 1 and path[1] in ("eukaryota", "eukariota"):
            stats["cellular_eukaryota"] += 1
    elif path and path[0] == "viral":
        stats["viral"] += 1
        if len(path) > 1 and path[1] == "phage":
            stats["viral_phage"] += 1
            if len(path) > 2 and path[2] == "structural":
                stats["phage_structural"] += 1
            elif len(path) > 2 and path[2] == "non_structural":
                stats["phage_non_structural"] += 1
        elif len(path) > 1 and path[1] in ("eukaryota", "eukariota"):
            stats["viral_eukaryota"] += 1
    stats["cluster_assigned"] += int(row.get("cluster_id", -1) not in (-1, None, ""))
    confidence = row.get("confidences", {}).get("M1")
    if confidence is not None:
        stats["sum_confidence_M1"] += float(confidence)


def finish_stats(stats: dict[str, Any]) -> dict[str, Any]:
    result = dict(stats)
    count = result.pop("sequences")
    confidence_sum = result.pop("sum_confidence_M1")
    length_sum = result.pop("sum_original_length_aa")
    result["sequences"] = count
    result["mean_original_length_aa"] = round(length_sum / count, 2) if count else 0
    result["mean_confidence_M1"] = round(confidence_sum / count, 6) if count else 0
    return result


def postprocess(raw_jsonl: Path, output_root: Path, manifest: list[dict[str, Any]]) -> dict[str, Any]:
    manifest_by_id = {row["seq_id"]: row for row in manifest}
    enriched_jsonl = output_root / "predicciones_completas.jsonl"
    full_csv = output_root / "predicciones_completas.csv"
    by_file: dict[str, dict[str, Any]] = defaultdict(new_stats)
    by_folder: dict[str, dict[str, Any]] = defaultdict(new_stats)
    overall = new_stats()
    source_count = 0
    # Branches emit different confidence/annotation fields. Discover the union
    # before writing instead of silently dropping fields absent from row one.
    csv_fields = dict.fromkeys(manifest[0]) if manifest else {}
    with raw_jsonl.open('r', encoding='utf-8') as source:
        for line in source:
            if line.strip():
                csv_fields.update(dict.fromkeys(flatten(json_safe(json.loads(line)))))

    with raw_jsonl.open("r", encoding="utf-8") as source, enriched_jsonl.open("w", encoding="utf-8") as destination_jsonl:
        first = source.readline()
        if not first:
            raise ValueError("Vydra no produjo predicciones")
        first_object = json_safe(json.loads(first))
        first_meta = manifest_by_id.pop(first_object.get("seq_id"), None)
        if first_meta is None:
            raise ValueError(f"ID no encontrado en el manifiesto: {first_object.get('seq_id')}")
        first_object.update(first_meta)
        columns = list(csv_fields)
        destination_csv = full_csv.open("w", encoding="utf-8", newline="")
        writer = csv.DictWriter(destination_csv, fieldnames=columns)
        writer.writeheader()

        def write_row(obj: dict[str, Any]) -> None:
            nonlocal source_count
            destination_jsonl.write(json.dumps(obj, ensure_ascii=False, allow_nan=False) + "\n")
            writer.writerow(flatten(obj))
            rel = obj["source_relative_path"]
            folder = obj["source_folder"] or "."
            add_result(overall, obj)
            add_result(by_file[rel], obj)
            add_result(by_folder[folder], obj)
            source_count += 1

        try:
            write_row(first_object)
            for line in source:
                if not line.strip():
                    continue
                obj = json_safe(json.loads(line))
                meta = manifest_by_id.pop(obj.get("seq_id"), None)
                if meta is None:
                    raise ValueError(f"ID duplicado o no encontrado en el manifiesto: {obj.get('seq_id')}")
                obj.update(meta)
                write_row(obj)
        finally:
            destination_csv.close()

    if source_count != len(manifest):
        raise ValueError(f"Vydra produjo {source_count} filas para {len(manifest)} entradas")

    summary_fields = [
        "source_relative_path", "source_folder", "source_file", "sequences", "cellular", "viral",
        "cellular_bacteria", "cellular_archaea", "cellular_eukaryota", "viral_phage", "viral_eukaryota",
        "phage_structural", "phage_non_structural", "cluster_assigned", "chunked",
        "mean_original_length_aa", "max_original_length_aa", "mean_confidence_M1",
    ]
    file_summary = []
    for rel, stats in sorted(by_file.items()):
        item = {"source_relative_path": rel, "source_folder": str(Path(rel).parent), "source_file": Path(rel).name}
        item.update(finish_stats(stats))
        file_summary.append(item)
    with (output_root / "resumen_por_archivo.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=summary_fields)
        writer.writeheader()
        writer.writerows(file_summary)

    folder_summary = []
    for folder, stats in sorted(by_folder.items()):
        item = {"source_folder": folder}
        item.update(finish_stats(stats))
        folder_summary.append(item)
    with (output_root / "resumen_por_carpeta.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["source_folder", *summary_fields[3:]])
        writer.writeheader()
        writer.writerows(folder_summary)

    summary = finish_stats(overall)
    write_json(output_root / "resumen_general.json", summary)
    raw_jsonl.unlink()
    return {"rows": source_count, "csv_columns": len(columns), "overall": summary}
