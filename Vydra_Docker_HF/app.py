from __future__ import annotations

import math
import csv
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel


BASE_DIR = Path(__file__).resolve().parent
WEB_DIR = BASE_DIR / "web"
JOB_DIR = BASE_DIR / "jobs"
JOB_DIR.mkdir(exist_ok=True)

app = FastAPI(title="Vydra Inference API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/assets", StaticFiles(directory=WEB_DIR / "assets"), name="assets")
vydra_module = None
jobs: dict[str, dict[str, Any]] = {}
jobs_lock = threading.Lock()
warmup_status = {"status": "pending", "error": None}


class InferenceRequest(BaseModel):
    sequence_or_fasta: str


def get_vydra():
    global vydra_module
    if vydra_module is None:
        import inference_gradio

        vydra_module = inference_gradio
    return vydra_module


def warmup_models():
    warmup_status["status"] = "loading"
    warmup_status["error"] = None
    try:
        vydra = get_vydra()
        vydra.preload_inference_artifacts()
        warmup_status["status"] = "ready"
        print("Vydra warmup complete: MLP weights, ProstT5, and prototype banks loaded.")
    except Exception as exc:
        warmup_status["status"] = "error"
        warmup_status["error"] = str(exc)
        print(f"Vydra warmup failed: {exc}")


@app.on_event("startup")
def startup_warmup():
    threading.Thread(target=warmup_models, daemon=True).start()


PART_ASSETS = {
    "baseplate": "assets/Parts/Baseplate.webp",
    "collar": "assets/Parts/Collar.webp",
    "head_tail_joining": "assets/Parts/Head-Tail_Joining.webp",
    "major_capsid": "assets/Parts/Major_Capsid.webp",
    "major_tail": "assets/Parts/Major_Tail.webp",
    "minor_capsid": "assets/Parts/Minor_Capsid.webp",
    "minor_tail": "assets/Parts/Minor_Tail.webp",
    "portal": "assets/Parts/Portal.webp",
    "tail_fiber": "assets/Parts/Tail_Fiber.webp",
    "tail_sheath": "assets/Parts/Tail_Sheath.webp",
    "non_structural": "assets/Parts/Non_Struct.webp",
    "viral_eukaryote": "assets/Parts/Viral_Euk.webp",
    "cellular": "assets/Parts/Cellular.webp",
    "bacteria": "assets/Parts/Cell_Bacteria.webp",
    "eukariota": "assets/Parts/Cell_Euk.webp",
    "archaea": "assets/Parts/Arhaea.webp",
    "viral": "assets/Parts/Viral.webp",
    "sequence": "assets/Parts/Seq_Protein.webp",
}

STRUCTURAL_LABELS = {
    "baseplate": "Baseplate",
    "collar": "Collar",
    "head_tail_joining": "Head-tail joining",
    "major_capsid": "Major capsid",
    "major_tail": "Major tail",
    "minor_capsid": "Minor capsid",
    "minor_tail": "Minor tail",
    "portal": "Portal",
    "tail_fiber": "Tail fiber",
    "tail_sheath": "Tail sheath",
}


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        out = float(value)
        if math.isnan(out):
            return default
        return out
    except (TypeError, ValueError):
        return default


def title_label(value: str) -> str:
    return value.replace("_", " ").replace("-", " ").title()


def prediction_description(class_key: str, path: list[str]) -> str:
    descriptions = {
        "major_capsid": "Proteina estructural mayor de capside, componente principal de la cabeza del fago.",
        "tail_fiber": "Proteina asociada al reconocimiento del hospedero y union inicial del fago.",
        "portal": "Componente del portal de empaquetamiento y salida del ADN viral.",
        "tail_sheath": "Componente contractil asociado a la cola del fago.",
        "non_structural": "Proteina de fago sin rol estructural directo; se reporta contexto por similitud.",
    }
    return descriptions.get(class_key, f"Prediccion final en la ruta {' / '.join(path)}.")


def class_icon_for(path: list[str], class_key: str) -> str:
    if class_key == "non_structural" or "non_structural" in path:
        return "assets/Non_Structural_Phage.webp"
    if class_key in STRUCTURAL_LABELS or "structural" in path:
        return "assets/Structural_Phage.webp"
    return "assets/protein.webp"


def visual_asset_for(path: list[str], class_key: str) -> str:
    if class_key in PART_ASSETS:
        return PART_ASSETS[class_key]
    if "non_structural" in path:
        return PART_ASSETS["non_structural"]
    if "phage" in path:
        return PART_ASSETS["viral"]
    if "cellular" in path:
        return PART_ASSETS["cellular"]
    return PART_ASSETS["sequence"]


def hierarchy_items(path: list[str], confidences: dict[str, float]) -> list[dict[str, Any]]:
    colors = ["coral", "green", "cyan", "blue", "violet"]
    scores = list(confidences.values())
    items = []
    for index, label in enumerate(path[:5]):
        score = scores[index] if index < len(scores) else scores[-1] if scores else 0.0
        items.append({
            "level": f"Nivel {index + 1}",
            "label": title_label(label),
            "score": safe_float(score),
            "color": colors[index % len(colors)],
        })
    return items


def cluster_payload(row: dict[str, Any]) -> dict[str, Any]:
    annotation = row.get("cluster_annotation") or {}
    cluster_id = row.get("cluster_id", -1)
    cluster_label = f"C{cluster_id}" if isinstance(cluster_id, int) and cluster_id >= 0 else "N/A"
    functions = []
    biological_label = row.get("cluster_biological_label") or ""
    if biological_label and biological_label != "unannotated":
        functions.append(biological_label)
    if annotation.get("best_taxonomic_level"):
        functions.append(f"Nivel: {annotation['best_taxonomic_level']}")
    if annotation.get("confidence"):
        functions.append(f"Confianza: {annotation['confidence']}")
    if not functions:
        functions = ["Contexto por similitud", "FAISS nearest neighbor", "Cluster biologico"]
    if annotation.get("dominant_product"):
        functions.insert(0, str(annotation["dominant_product"]))
    elif annotation.get("representative_product"):
        functions.insert(0, str(annotation["representative_product"]))

    organisms = [
        annotation.get("dominant_virus_name"),
        annotation.get("dominant_family"),
        annotation.get("dominant_genus"),
        annotation.get("dominant_host"),
    ]
    organisms = [str(item) for item in organisms if item]
    if annotation.get("families_in_cluster") and annotation.get("families_in_cluster") not in organisms:
        organisms.append(f"Families: {annotation['families_in_cluster']}")
    if not organisms:
        organisms = [row.get("cluster_nearest_seq_id") or "Referencia mas cercana N/A"]

    return {
        "id": cluster_label,
        "size": int(safe_float(annotation.get("n_sequences"), 0)),
        "avg_similarity": safe_float(row.get("cluster_similarity"), 0.0),
        "functions": functions[:3],
        "organisms": organisms[:4],
        "nearest_seq_id": row.get("cluster_nearest_seq_id") or "",
        "threshold": row.get("cluster_similarity_threshold") or "",
        "annotation": annotation,
    }


def class_context_payload(row: dict[str, Any]) -> dict[str, Any]:
    metadata = row.get("viral_euk_class_metadata") or {}
    class_number = str(metadata.get("class_number") or "").strip()
    if not class_number:
        return {"kind": "none", "metadata": {}}

    functions = [
        metadata.get("protein_description"),
        metadata.get("protein_function_class"),
        metadata.get("molecule_type"),
    ]
    functions = [str(item) for item in functions if str(item or "").strip()]

    organisms = [
        metadata.get("family_label_ncbi_2023"),
        metadata.get("genus"),
        metadata.get("host"),
        metadata.get("families_in_class_2021"),
    ]
    organisms = [str(item) for item in organisms if str(item or "").strip()]

    return {
        "kind": "viral_euk_class",
        "id": f"Class {class_number}",
        "size": int(safe_float(metadata.get("sequences_per_class"), 0)),
        "avg_similarity": 0.0,
        "functions": functions[:3] or ["VirDetect-AI class dictionary"],
        "organisms": organisms[:4] or ["Metadata N/A"],
        "nearest_seq_id": metadata.get("cluster_rep_sequence_accession") or "",
        "threshold": "",
        "annotation": metadata,
    }


def biological_context_payload(row: dict[str, Any]) -> dict[str, Any]:
    class_context = class_context_payload(row)
    if class_context["kind"] != "none":
        return class_context
    cluster = cluster_payload(row)
    cluster["kind"] = "phage_cluster" if cluster.get("id") != "N/A" else "none"
    return cluster


def to_service_result(record: Any, prediction: dict[str, Any], elapsed_seconds: float) -> dict[str, Any]:
    path = [str(item) for item in prediction["path"]]
    final_key = str(path[-1]) if path else "sequence"
    if final_key == "phage_non_struct":
        final_key = "non_structural"
    class_label = STRUCTURAL_LABELS.get(final_key, title_label(final_key))
    route_label = " - ".join(title_label(item) for item in path[:3]) if path else "Unknown"
    confidence_values = list(prediction.get("confidences", {}).values())
    confidence = safe_float(confidence_values[-1] if confidence_values else 0.0)
    confidence_label = "Muy alta" if confidence >= 0.9 else "Alta" if confidence >= 0.8 else "Media" if confidence >= 0.6 else "Baja"

    row = {"seq_id": record.seq_id, "sequence": record.sequence, **prediction}
    context = biological_context_payload(row)
    return {
        "query_id": record.seq_id,
        "elapsed_seconds": elapsed_seconds,
        "status": "Prediccion completa",
        "prediction": {
            "route_label": route_label,
            "class_key": final_key,
            "class_label": class_label,
            "class_icon": class_icon_for(path, final_key),
            "visual_asset": visual_asset_for(path, final_key),
            "description": prediction_description(final_key, path),
        },
        "confidence": {"value": confidence, "label": confidence_label},
        "hierarchy": hierarchy_items(path, prediction.get("confidences", {})),
        "cluster": context,
        "class_context": class_context_payload(row),
    }


def result_csv_row(result: dict[str, Any]) -> dict[str, Any]:
    prediction = result["prediction"]
    confidence = result["confidence"]
    cluster = result["cluster"]
    return {
        "query_id": result["query_id"],
        "elapsed_seconds": result["elapsed_seconds"],
        "route_label": prediction["route_label"],
        "class_key": prediction["class_key"],
        "class_label": prediction["class_label"],
        "confidence": confidence["value"],
        "confidence_label": confidence["label"],
        "cluster_id": cluster["id"],
        "cluster_size": cluster["size"],
        "cluster_avg_similarity": cluster["avg_similarity"],
        "cluster_nearest_seq_id": cluster.get("nearest_seq_id", ""),
        "cluster_threshold": cluster.get("threshold", ""),
        "hierarchy": " > ".join(item["label"] for item in result["hierarchy"]),
        "cluster_functions": " | ".join(cluster.get("functions", [])),
        "cluster_organisms": " | ".join(cluster.get("organisms", [])),
        "viral_euk_class_number": cluster.get("annotation", {}).get("class_number", ""),
        "viral_euk_rep_accession": cluster.get("annotation", {}).get("cluster_rep_sequence_accession", ""),
        "viral_euk_family_2023": cluster.get("annotation", {}).get("family_label_ncbi_2023", ""),
        "viral_euk_protein_description": cluster.get("annotation", {}).get("protein_description", ""),
        "viral_euk_protein_function_class": cluster.get("annotation", {}).get("protein_function_class", ""),
        "viral_euk_host": cluster.get("annotation", {}).get("host", ""),
        "viral_euk_molecule_type": cluster.get("annotation", {}).get("molecule_type", ""),
        "viral_euk_genus": cluster.get("annotation", {}).get("genus", ""),
        "phage_representative_seq_id": cluster.get("annotation", {}).get("representative_seq_id", ""),
        "phage_representative_accession": cluster.get("annotation", {}).get("representative_accession", ""),
        "phage_representative_product": cluster.get("annotation", {}).get("representative_product", ""),
        "phage_representative_organism": cluster.get("annotation", {}).get("representative_organism", ""),
        "phage_length_min": cluster.get("annotation", {}).get("min_length", ""),
        "phage_length_max": cluster.get("annotation", {}).get("max_length", ""),
        "phage_length_mean": cluster.get("annotation", {}).get("mean_length", ""),
        "phage_length_std": cluster.get("annotation", {}).get("std_length", ""),
        "phage_families_in_cluster": cluster.get("annotation", {}).get("families_in_cluster", ""),
        "phage_genera_in_cluster": cluster.get("annotation", {}).get("genera_in_cluster", ""),
        "phage_hosts_in_cluster": cluster.get("annotation", {}).get("hosts_in_cluster", ""),
        "phage_products_in_cluster": cluster.get("annotation", {}).get("products_in_cluster", ""),
    }


def write_results_csv(job_id: str, results: list[dict[str, Any]]) -> str:
    path = JOB_DIR / f"{job_id}_results.csv"
    rows = [result_csv_row(result) for result in results]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    return str(path)


def set_job(job_id: str, **updates):
    with jobs_lock:
        jobs[job_id].update(updates)


def infer_records(records: list[Any], job_id: str | None = None) -> dict[str, Any]:
    vydra = get_vydra()
    if not records:
        raise HTTPException(status_code=400, detail="No valid protein sequence found.")

    start = time.perf_counter()

    def progress(processed: int, total: int):
        if job_id:
            set_job(job_id, processed=processed, total=total, stage="prostt5")

    embeddings = vydra.embed_records(records, progress_callback=progress)
    elapsed = time.perf_counter() - start
    results = []
    for record, embedding in zip(records, embeddings):
        prediction = vydra.run_hierarchy(embedding)
        results.append(to_service_result(record, prediction, elapsed))
    csv_path = write_results_csv(job_id or uuid.uuid4().hex, results)
    return {"result": results[0], "results": results, "csv_path": csv_path}


def infer_text(sequence_or_fasta: str) -> dict[str, Any]:
    vydra = get_vydra()
    records = vydra.parse_fasta_text(sequence_or_fasta or "")
    output = infer_records(records)
    return {"result": output["result"], "results": output["results"]}


def run_job(job_id: str, records: list[Any]):
    try:
        output = infer_records(records, job_id=job_id)
        set_job(
            job_id,
            status="complete",
            stage="complete",
            processed=len(records),
            results=output["results"],
            result=output["result"],
            csv_path=output["csv_path"],
        )
    except Exception as exc:
        set_job(job_id, status="error", stage="error", error=str(exc))


def start_job_from_text(sequence_or_fasta: str) -> dict[str, Any]:
    vydra = get_vydra()
    records = vydra.parse_fasta_text(sequence_or_fasta or "")
    if not records:
        raise HTTPException(status_code=400, detail="No valid protein sequence found.")
    job_id = uuid.uuid4().hex
    with jobs_lock:
        jobs[job_id] = {
            "status": "running",
            "stage": "queued",
            "total": len(records),
            "processed": 0,
            "results": [],
            "result": None,
            "csv_path": None,
            "error": None,
        }
    thread = threading.Thread(target=run_job, args=(job_id, records), daemon=True)
    thread.start()
    return {"job_id": job_id, "total": len(records), "processed": 0, "status": "running"}


@app.get("/")
def index():
    return FileResponse(WEB_DIR / "index.html", headers={"Cache-Control": "no-store"})


@app.get("/styles.css")
def styles():
    return FileResponse(WEB_DIR / "styles.css", headers={"Cache-Control": "no-store"})


@app.get("/script.js")
def script():
    return FileResponse(WEB_DIR / "script.js", headers={"Cache-Control": "no-store"})


@app.get("/health")
def health():
    return {"ok": True, "warmup": warmup_status}


@app.post("/api/infer")
def api_infer(request: InferenceRequest):
    return infer_text(request.sequence_or_fasta)


@app.post("/api/jobs")
def api_start_job(request: InferenceRequest):
    return start_job_from_text(request.sequence_or_fasta)


@app.post("/api/infer-file")
async def api_infer_file(file: UploadFile = File(...)):
    raw = await file.read()
    text = raw.decode("utf-8", errors="replace")
    return infer_text(text)


@app.post("/api/jobs-file")
async def api_start_job_file(file: UploadFile = File(...)):
    raw = await file.read()
    text = raw.decode("utf-8", errors="replace")
    return start_job_from_text(text)


@app.get("/api/jobs/{job_id}")
def api_job_status(job_id: str):
    with jobs_lock:
        job = jobs.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        payload = dict(job)
    payload["download_url"] = f"/api/jobs/{job_id}/download" if payload.get("csv_path") else None
    return payload


@app.get("/api/jobs/{job_id}/download")
def api_job_download(job_id: str):
    with jobs_lock:
        job = jobs.get(job_id)
        if not job or not job.get("csv_path"):
            raise HTTPException(status_code=404, detail="CSV not found")
        path = Path(job["csv_path"])
    if not path.exists():
        raise HTTPException(status_code=404, detail="CSV not found")
    return FileResponse(path, media_type="text/csv", filename="vydra_results.csv")
