"""Command line interface for the self-contained Vydra inference bundle."""

from __future__ import annotations

import argparse
import contextlib
import csv
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import warnings
from pathlib import Path
from typing import Any, Iterable
from urllib.error import HTTPError
from urllib.request import urlopen


BASE_DIR = Path(__file__).resolve().parent
ARTIFACTS_DIR = BASE_DIR / "artifacts"
WEIGHTS_DIR = BASE_DIR / "models" / "mlp_weights"
BUNDLED_PROSTT5_DIR = BASE_DIR / "models" / "prostt5"

MODEL_NAMES = (
    "M1_L1_viral_vs_cellular",
    "M2_cellular_3_clases",
    "M3_viral_phage_vs_euk",
    "M4_viral_euk_978_clases",
    "M5_phage_structural_vs_non",
    "M6_structural_10_clases",
)

REQUIRED_ARTIFACTS = (
    "label_classes.json",
    "Struct_prototype_bank.pt",
    "Non_Struct_prototype_bank.pt",
    "cluster_taxonomy_summary.csv",
    "viral_euk_class_metadata.csv",
    "recommended_thresholds_config.json",
)

RELEASE_TAG = "artifacts-v1"
RELEASE_BASE_URL = f"https://github.com/Maxdesigna7x/Vydra/releases/download/{RELEASE_TAG}"
DOWNLOADABLE_ARTIFACTS = {
    "Struct_prototype_bank.pt": "30958545dee5e5e10483b682ef438bb6a950699c25936782ff6ae0b5b8fe286a",
    "Non_Struct_prototype_bank.pt": "889302cc05074090ccb908a27957d0b383438475d246f54ff4779ee99d83aed8",
}


def eprint(*values: object) -> None:
    print(*values, file=sys.stderr)


def import_engine(device_name: str, offline: bool):
    """Import the existing inference engine while keeping stdout machine-readable."""
    if offline:
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"

    if str(BASE_DIR) not in sys.path:
        sys.path.insert(0, str(BASE_DIR))
    with contextlib.redirect_stdout(sys.stderr), warnings.catch_warnings():
        warnings.filterwarnings("ignore", message="The parameters have been moved from the Blocks constructor")
        import inference_gradio as engine

    if device_name != "auto":
        import torch

        if device_name == "cuda" and not torch.cuda.is_available():
            raise RuntimeError("Se solicito CUDA, pero PyTorch no detecta una GPU compatible")
        engine.device = torch.device(device_name)

    model_dir = os.environ.get("VYDRA_PROSTT5_PATH")
    if model_dir:
        resolved = Path(model_dir).expanduser().resolve()
        if not resolved.exists():
            raise FileNotFoundError(f"VYDRA_PROSTT5_PATH no existe: {resolved}")
        engine.MODEL_NAME = str(resolved)
    elif BUNDLED_PROSTT5_DIR.exists():
        engine.MODEL_NAME = str(BUNDLED_PROSTT5_DIR)
    return engine


def rows_from_records(engine, records, embeddings) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for record, embedding in zip(records, embeddings):
        prediction = engine.run_hierarchy(embedding)
        rows.append(
            {
                "seq_id": record.seq_id,
                "length": record.original_length,
                "chunked": record.chunked,
                **prediction,
            }
        )
    return rows


def flatten_row(row: dict[str, Any]) -> dict[str, Any]:
    flat: dict[str, Any] = {}
    for key, value in row.items():
        if isinstance(value, dict):
            for nested_key, nested_value in value.items():
                flat[f"{key}.{nested_key}"] = nested_value
        elif isinstance(value, list):
            flat[key] = "/".join(str(item) for item in value)
        else:
            flat[key] = value
    return flat


def json_safe(value: Any) -> Any:
    try:
        import numpy as np

        if isinstance(value, np.generic):
            return value.item()
        if isinstance(value, float) and (np.isnan(value) or np.isinf(value)):
            return None
    except ImportError:
        pass
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(v) for v in value]
    return value


def write_csv(rows: list[dict[str, Any]], stream) -> None:
    flat_rows = [flatten_row(json_safe(row)) for row in rows]
    fields: list[str] = []
    for row in flat_rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    writer = csv.DictWriter(stream, fieldnames=fields)
    writer.writeheader()
    writer.writerows(flat_rows)


def render_table(rows: Iterable[dict[str, Any]], stream) -> None:
    rows = list(rows)
    headers = ("ID", "LONGITUD", "RUTA", "CLUSTER", "SIMILITUD")
    values = []
    for row in rows:
        cluster = row.get("cluster_id", -1)
        similarity = row.get("cluster_similarity")
        similarity_text = "-"
        if isinstance(similarity, (int, float)) and similarity == similarity:
            similarity_text = f"{similarity:.4f}"
        values.append(
            (
                str(row.get("seq_id", "")),
                str(row.get("length", "")),
                str(row.get("path_text", "")),
                "-" if cluster in (-1, None, "") else str(cluster),
                similarity_text,
            )
        )
    widths = [len(header) for header in headers]
    for row in values:
        widths = [max(width, len(value)) for width, value in zip(widths, row)]
    print("  ".join(header.ljust(width) for header, width in zip(headers, widths)), file=stream)
    print("  ".join("-" * width for width in widths), file=stream)
    for row in values:
        print("  ".join(value.ljust(width) for value, width in zip(row, widths)), file=stream)


def emit(rows: list[dict[str, Any]], output_format: str, output: str | None) -> None:
    stream = open(output, "w", encoding="utf-8", newline="") if output else sys.stdout
    try:
        safe_rows = json_safe(rows)
        if output_format == "json":
            json.dump(safe_rows, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        elif output_format == "jsonl":
            for row in safe_rows:
                stream.write(json.dumps(row, ensure_ascii=False) + "\n")
        elif output_format == "csv":
            write_csv(safe_rows, stream)
        else:
            render_table(safe_rows, stream)
    finally:
        if output:
            stream.close()
            eprint(f"Resultados guardados en {Path(output).resolve()}")


def command_predict(args: argparse.Namespace) -> int:
    engine = import_engine(args.device, args.offline)

    if args.embedding:
        with contextlib.redirect_stdout(sys.stderr):
            # The web helper treats objects with a ``name`` attribute as upload
            # objects. Pass a string so pathlib.Path.name does not strip the
            # parent directory from a normal CLI path.
            records, embeddings = engine.load_embedding_file(str(args.embedding.resolve()))
    else:
        if args.offline and not any(path.exists() for path in model_cache_candidates()):
            raise RuntimeError(
                "ProstT5 no esta disponible localmente. Ejecuta 'vydra download-model' "
                "una vez con red, define VYDRA_PROSTT5_PATH, o usa --embedding."
            )
        if args.seq is not None:
            text = args.seq
        elif args.fasta is not None:
            text = Path(args.fasta).read_text(encoding="utf-8")
        else:
            text = sys.stdin.read()
        records = engine.parse_fasta_text(text)
        if not records:
            raise ValueError("No se encontro ninguna secuencia valida")
        eprint(f"Generando embeddings de {len(records)} secuencia(s)...")
        with contextlib.redirect_stdout(sys.stderr):
            embeddings = engine.embed_records(records)

    eprint(f"Clasificando {len(records)} registro(s) en {engine.device}...")
    with contextlib.redirect_stdout(sys.stderr):
        rows = rows_from_records(engine, records, embeddings)
    emit(rows, args.format, args.output)
    return 0


def model_cache_candidates() -> list[Path]:
    paths = [BUNDLED_PROSTT5_DIR]
    configured = os.environ.get("VYDRA_PROSTT5_PATH")
    if configured:
        paths.insert(0, Path(configured).expanduser())
    hf_home = Path(os.environ.get("HF_HOME", Path.home() / ".cache" / "huggingface"))
    paths.append(hf_home / "hub" / "models--Rostlab--ProstT5")
    return paths


def command_doctor(_: argparse.Namespace) -> int:
    problems = 0
    print("Vydra CLI - diagnostico\n")
    print(f"Paquete: {BASE_DIR}")

    for module in ("torch", "transformers", "sentencepiece", "faiss", "numpy", "pandas"):
        found = importlib.util.find_spec(module) is not None
        print(f"[{'OK' if found else 'FALTA'}] dependencia {module}")
        problems += int(not found)

    for model_name in MODEL_NAMES:
        path = WEIGHTS_DIR / f"{model_name}.pth"
        print(f"[{'OK' if path.is_file() else 'FALTA'}] {path.relative_to(BASE_DIR)}")
        problems += int(not path.is_file())

    for name in REQUIRED_ARTIFACTS:
        path = ARTIFACTS_DIR / name
        print(f"[{'OK' if path.is_file() else 'FALTA'}] {path.relative_to(BASE_DIR)}")
        problems += int(not path.is_file())

    local_prostt5 = next((path for path in model_cache_candidates() if path.exists()), None)
    if local_prostt5:
        print(f"[OK] ProstT5 local: {local_prostt5}")
    else:
        print("[AVISO] ProstT5 no esta guardado localmente; las secuencias requeriran descargarlo una vez")

    if problems:
        print(f"\nDiagnostico: {problems} problema(s) que impiden la inferencia.")
        return 1
    print("\nDiagnostico: artefactos Vydra listos.")
    return 0


def command_download_model(args: argparse.Namespace) -> int:
    try:
        from huggingface_hub import snapshot_download
    except ImportError as exc:
        raise RuntimeError("Falta huggingface_hub; instala las dependencias de Vydra") from exc
    target = Path(args.directory).expanduser().resolve() if args.directory else BUNDLED_PROSTT5_DIR
    target.mkdir(parents=True, exist_ok=True)
    eprint(f"Descargando Rostlab/ProstT5 en {target}...")
    snapshot_download(repo_id="Rostlab/ProstT5", local_dir=target)
    print(target)
    return 0


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def command_download_artifacts(args: argparse.Namespace) -> int:
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    for filename, expected_hash in DOWNLOADABLE_ARTIFACTS.items():
        destination = ARTIFACTS_DIR / filename
        if destination.exists() and not args.force:
            eprint(f"Ya existe: {destination}")
            continue
        partial = destination.with_suffix(destination.suffix + ".part")
        url = f"{RELEASE_BASE_URL}/{filename}"
        eprint(f"Descargando {filename}...")
        downloaded_path = partial
        try:
            with urlopen(url) as response, partial.open("wb") as output:
                total = int(response.headers.get("Content-Length", 0))
                copied = 0
                while True:
                    chunk = response.read(8 * 1024 * 1024)
                    if not chunk:
                        break
                    output.write(chunk)
                    copied += len(chunk)
                    if total:
                        eprint(f"  {copied / total:6.1%}", end="\r")
            if total:
                eprint(" " * 20, end="\r")
        except HTTPError as exc:
            partial.unlink(missing_ok=True)
            if exc.code not in {401, 403, 404} or not shutil.which("gh"):
                raise RuntimeError(
                    "No se pudo descargar el artefacto. Si el repositorio es privado, "
                    "instala GitHub CLI y ejecuta 'gh auth login'."
                ) from exc
            eprint("El repositorio requiere autenticacion; usando GitHub CLI...")
            try:
                subprocess.run(
                    [
                        "gh", "release", "download", RELEASE_TAG,
                        "--repo", "Maxdesigna7x/Vydra",
                        "--pattern", filename,
                        "--dir", str(ARTIFACTS_DIR),
                        "--clobber",
                    ],
                    check=True,
                )
            except subprocess.CalledProcessError as download_error:
                raise RuntimeError("GitHub CLI no pudo descargar el artefacto") from download_error
            downloaded_path = destination
        actual_hash = sha256_file(downloaded_path)
        if actual_hash != expected_hash:
            downloaded_path.unlink(missing_ok=True)
            raise RuntimeError(f"Checksum invalido para {filename}")
        if downloaded_path == partial:
            partial.replace(destination)
        eprint(f"Listo: {destination}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="vydra",
        description="Clasificador jerarquico local de proteinas Vydra.",
    )
    parser.add_argument("--version", action="version", version="Vydra CLI 0.1.0")
    subparsers = parser.add_subparsers(dest="command", required=True)

    predict = subparsers.add_parser("predict", help="clasificar secuencias o embeddings")
    source = predict.add_mutually_exclusive_group(required=True)
    source.add_argument("--seq", help="secuencia de aminoacidos o texto FASTA")
    source.add_argument("--fasta", type=Path, help="archivo FASTA/TXT")
    source.add_argument("--embedding", type=Path, help="archivo de embeddings .pt o .npy")
    source.add_argument("--stdin", action="store_true", help="leer secuencia/FASTA desde stdin")
    predict.add_argument("--format", choices=("table", "json", "jsonl", "csv"), default="table")
    predict.add_argument("-o", "--output", help="guardar resultado en un archivo")
    predict.add_argument("--device", choices=("auto", "cpu", "cuda"), default="auto")
    predict.add_argument("--offline", action="store_true", help="prohibir descargas y usar solo archivos locales")
    predict.set_defaults(func=command_predict)

    doctor = subparsers.add_parser("doctor", help="comprobar dependencias, pesos y artefactos")
    doctor.set_defaults(func=command_doctor)

    download = subparsers.add_parser("download-model", help="guardar ProstT5 dentro del paquete")
    download.add_argument("--directory", help="directorio de destino (por defecto models/prostt5)")
    download.set_defaults(func=command_download_model)

    artifacts = subparsers.add_parser(
        "download-artifacts",
        help="descargar los bancos de prototipos publicados en GitHub Releases",
    )
    artifacts.add_argument("--force", action="store_true", help="reemplazar archivos existentes")
    artifacts.set_defaults(func=command_download_artifacts)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except (OSError, ValueError, RuntimeError, ImportError) as exc:
        eprint(f"Error: {exc}")
        return 2
    except KeyboardInterrupt:
        eprint("Interrumpido por el usuario")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
