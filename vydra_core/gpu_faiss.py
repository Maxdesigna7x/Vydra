"""CPU and GPU FAISS indexes shared by the CLI and local GUI inference engine."""

from __future__ import annotations

import threading

import faiss
import numpy as np
import torch


# Keep resources alive for as long as their indexes, and serialize access:
# StandardGpuResources cannot serve concurrent searches from local inference threads.
_lock = threading.RLock()
_resources: dict[int, object] = {}


def require_gpu(device_id: int | None = None) -> tuple[object, int]:
    """Validate CUDA and GPU FAISS without ever falling back to a CPU index."""
    if not torch.cuda.is_available():
        raise RuntimeError(
            "FAISS requiere una GPU CUDA accesible. La inferencia se detiene; "
            "Select CPU or Automatic to run without CUDA."
        )
    for name in ("StandardGpuResources", "GpuIndexFlatIP", "GpuIndexFlatConfig", "GpuIndex", "get_num_gpus"):
        if not callable(getattr(faiss, name, None)):
            raise RuntimeError(
                "La instalacion de FAISS no tiene soporte GPU. Usa el entorno "
                "Conda de Vydra con faiss-gpu; or select CPU / Automatic with faiss-cpu."
            )
    selected = torch.cuda.current_device() if device_id is None else device_id
    if selected < 0 or selected >= faiss.get_num_gpus():
        raise RuntimeError(f"FAISS no puede acceder a la GPU CUDA:{selected}; no se usara CPU.")
    with _lock:
        if selected not in _resources:
            try:
                resource = faiss.StandardGpuResources()
                resource.setTempMemory(256 * 1024 * 1024)
                resource.setDefaultNullStreamAllDevices()
                # Initialize the selected device now, before any ProstT5 work.
                resource.getDefaultStream(selected)
            except Exception as exc:
                raise RuntimeError(
                    f"No se pudo inicializar FAISS en CUDA:{selected}; no se usara CPU: {exc}"
                ) from exc
            _resources[selected] = resource
            print(f"FAISS backend: GPU CUDA:{selected} (GpuIndexFlatIP, float32)")
        return _resources[selected], selected


def select_device(requested="auto"):
    """Resolve one device for models and FAISS; explicit CUDA never falls back."""
    requested = str(requested)
    if requested == "cpu":
        return torch.device("cpu")
    if requested == "auto":
        try:
            require_gpu()
            return torch.device("cuda")
        except RuntimeError:
            return torch.device("cpu")
    selected = torch.device(requested)
    if selected.type != "cuda":
        raise ValueError(f"Unsupported inference device: {requested}")
    require_gpu(selected.index)
    return selected


def require_backend(device):
    selected = torch.device(device)
    if selected.type == "cuda":
        return require_gpu(selected.index)
    if not callable(getattr(faiss, "IndexFlatIP", None)):
        raise RuntimeError("FAISS CPU indexes are unavailable; install faiss-cpu or faiss-gpu.")
    return None, None


def build_index(vectors: np.ndarray, device_id: int | None = None, *, device="cuda"):
    resource, selected = require_backend(torch.device("cuda", device_id) if str(device) == "cuda" else device)
    matrix = np.ascontiguousarray(vectors, dtype=np.float32)
    if matrix.ndim != 2 or matrix.shape[1] == 0:
        raise ValueError(f"Invalid FAISS prototype matrix: {matrix.shape}")
    if resource is None:
        index = faiss.IndexFlatIP(matrix.shape[1])
        index.add(matrix)
        return index
    with _lock:
        config = faiss.GpuIndexFlatConfig()
        config.device = selected
        config.useFloat16 = False
        try:
            index = faiss.GpuIndexFlatIP(resource, matrix.shape[1], config)
            index.add(matrix)
        except Exception as exc:
            raise RuntimeError(
                f"No se pudo crear/cargar el indice FAISS en CUDA:{selected}; "
                f"no se usara CPU: {exc}"
            ) from exc
        return index


def search_index(index, queries: np.ndarray, k: int = 1):
    gpu_type = getattr(faiss, "GpuIndex", None)
    if not isinstance(index, faiss.IndexFlatIP) and (gpu_type is None or not isinstance(index, gpu_type)):
        raise TypeError("Expected a CPU or GPU FAISS inner-product index.")
    with _lock:
        return index.search(np.ascontiguousarray(queries, dtype=np.float32), k)
