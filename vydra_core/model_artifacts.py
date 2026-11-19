"""Explicit checkpoint and class-order adapters for frozen Vydra models."""
from __future__ import annotations

import json
import hashlib
from pathlib import Path


def load_runtime_mlp(checkpoint, num_classes: int, class_labels=None):
    """Load baseline or self-describing search weights with strict shape checks."""
    import torch
    from torch import nn

    config = checkpoint.get("config")
    if config is None:
        config = {"widths": [512, 256], "dropout": [0.3, 0.2], "batch_norm": True}
    widths, dropout = config["widths"], config["dropout"]
    if (widths, dropout, config["batch_norm"]) not in (
        ([512, 256], [0.3, 0.2], True),
        ([1024, 512, 256], [0.35, 0.25, 0.15], True),
    ):
        raise ValueError("Unsupported runtime MLP architecture")
    if checkpoint.get("n_classes", num_classes) != num_classes:
        raise ValueError("Checkpoint class count differs from runtime labels")
    if class_labels is not None and "label_classes" in checkpoint:
        if list(map(str, checkpoint["label_classes"])) != list(map(str, class_labels)):
            raise ValueError("Checkpoint class order differs from runtime labels")
    layers = []
    in_dim = 1024
    for width, drop in zip(widths, dropout):
        layers.extend([nn.Linear(in_dim, width), nn.BatchNorm1d(width), nn.ReLU(), nn.Dropout(drop)])
        in_dim = width
    layers.append(nn.Linear(in_dim, num_classes))
    from collections import OrderedDict
    model = nn.Sequential(OrderedDict([("net", nn.Sequential(*layers))]))
    state = state_for_runtime(checkpoint)
    for tensor in state.values():
        if tensor.is_floating_point() and not torch.isfinite(tensor).all():
            raise ValueError("Nonfinite checkpoint tensor")
    model.load_state_dict(state, strict=True)
    return model.eval()


def state_for_runtime(state):
    """Rename Stage 5's module prefix without changing any tensor or row order."""
    for key in ("state_dict", "model_state_dict"):
        if key in state and isinstance(state[key], dict):
            state = state[key]
            break
    if state and all(key.startswith("layers.") for key in state):
        return {"net." + key[len("layers."):]: value for key, value in state.items()}
    return state


def load_class_order(path: Path) -> dict[str, list[str]]:
    """Read either the Stage 5 indexed manifest or the runtime flat mapping."""
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if "tasks" not in raw:
        return raw
    result = {}
    for task in raw["tasks"].values():
        classes = sorted(task["classes"], key=lambda row: row["index"])
        if [row["index"] for row in classes] != list(range(len(classes))):
            raise ValueError(f"Non-contiguous class indices for {task['name']}")
        labels = [str(row["label"]) for row in classes]
        if len(set(labels)) != len(labels):
            raise ValueError(f"Duplicate class labels for {task['name']}")
        result[task["name"]] = labels
    return result


def file_sha256(path: Path) -> str:
    """Return a streaming SHA-256 digest without loading large model files at once."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_canonical_reference_release(
    release: dict,
    training: dict,
    artifacts_dir: Path,
    weights_dir: Path | None = None,
) -> None:
    """Fail closed unless the active reference files match the promoted train-only release."""
    if release.get("status") != "promoted":
        raise RuntimeError("Canonical reference release is not promoted")
    if release.get("partition") != "train_only":
        raise RuntimeError("Canonical references must come from the train-only partition")
    if training.get("status") != "complete":
        raise RuntimeError("Stage 5 training manifest is not complete")
    if release.get("model_source_run") != training.get("run_id"):
        raise RuntimeError("Model and reference release provenance do not match")
    if release.get("embedding_cache_sha256") != training.get("source_hashes", {}).get("cache_X_embeddings_l2.npy"):
        raise RuntimeError("Model and reference release use different embedding caches")

    # Promoted releases bind the six runtime checkpoints to the exact training
    # run. Legacy manifests remain readable for rollback, while any release
    # declaring a release_id must carry checkpoint hashes and verify them.
    checkpoint_manifest = release.get("model_checkpoints")
    if release.get("release_id"):
        if not isinstance(checkpoint_manifest, dict) or not checkpoint_manifest:
            raise RuntimeError("Active release is missing its runtime checkpoint checksum map")
        training_runs = {
            str(row.get("run_name")): str(row.get("checkpoint_sha256"))
            for row in training.get("results", [])
            if isinstance(row, dict) and row.get("status") == "completed"
        }
        if weights_dir is None:
            raise RuntimeError("Active release verification requires a runtime model directory")
        for filename, entry in checkpoint_manifest.items():
            relative = Path(filename)
            if relative.is_absolute() or len(relative.parts) != 1 or relative.name != filename:
                raise RuntimeError(f"Invalid runtime checkpoint path: {filename!r}")
            if not isinstance(entry, dict):
                raise RuntimeError(f"Invalid runtime checkpoint manifest entry: {filename}")
            run_name = str(entry.get("training_run_name", ""))
            expected = str(entry.get("sha256", ""))
            if not expected or training_runs.get(run_name) != expected:
                raise RuntimeError(f"Runtime checkpoint provenance mismatch: {filename}")
            checkpoint = Path(weights_dir) / relative
            if not checkpoint.is_file() or file_sha256(checkpoint) != expected:
                raise RuntimeError(f"Runtime checkpoint checksum mismatch: {filename}")
        diagnostic = release.get("diagnostic_checkpoint")
        if diagnostic is not None:
            if not isinstance(diagnostic, dict):
                raise RuntimeError("Invalid diagnostic checkpoint manifest")
            relative = Path(str(diagnostic.get("runtime_path", "")))
            if relative.is_absolute() or not relative.parts or ".." in relative.parts:
                raise RuntimeError("Invalid diagnostic checkpoint path")
            run_name = str(diagnostic.get("training_run_name", ""))
            expected = str(diagnostic.get("sha256", ""))
            checkpoint = Path(weights_dir) / relative
            if not expected or training_runs.get(run_name) != expected:
                raise RuntimeError("Diagnostic checkpoint provenance mismatch")
            if not checkpoint.is_file() or file_sha256(checkpoint) != expected:
                raise RuntimeError("Diagnostic checkpoint checksum mismatch")

    required = {
        "Struct_id_cluster_map.csv",
        "Non_Struct_id_cluster_map.csv",
        "Struct_prototype_bank.pt",
        "Non_Struct_prototype_bank.pt",
        "cluster_taxonomy_summary.csv",
        "recommended_thresholds_config.json",
        "prototype_sequence_metadata.csv.gz",
    }
    files = release.get("files")
    if not isinstance(files, dict) or not required.issubset(files):
        missing = sorted(required - set(files or {}))
        raise RuntimeError(f"Canonical reference manifest is missing required artifacts: {missing}")

    root = Path(artifacts_dir).resolve()
    for name, expected in files.items():
        # The manifest is intentionally flat: reject paths that could escape
        # the active runtime artifact directory.
        relative = Path(name)
        if relative.is_absolute() or len(relative.parts) != 1 or relative.name != name:
            raise RuntimeError(f"Invalid canonical reference artifact path: {name!r}")
        path = (root / relative).resolve()
        if path.parent != root or not path.is_file():
            raise RuntimeError(f"Missing canonical reference artifact: {root / relative}")
        if not isinstance(expected, str) or file_sha256(path) != expected:
            raise RuntimeError(f"Canonical reference artifact checksum mismatch: {name}")
