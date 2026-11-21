"""Shared local inference model catalog and artifact verification."""
import hashlib
import json
import os
from pathlib import Path

PROFILES = {
    "prostt5": dict(name="ProstT5", dimension=1024, size="5.64 GB", speed="1×"),
    "esm2-150m": dict(name="ESM-2 150M", dimension=640, size="595 MB", speed="≈8.5×"),
    "esm2-35m": dict(name="ESM-2 35M", dimension=480, size="136 MB", speed="≈31×"),
    "esm2-8m": dict(name="ESM-2 8M", dimension=320, size="31 MB", speed="≈97×"),
}


def profile_root():
    return Path(os.environ.get("VYDRA_PROFILE_ROOT", Path.home() / ".local/share/vydra/profiles")).expanduser()


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 2**20), b""):
            digest.update(block)
    return digest.hexdigest()


def profile_files(directory, filename, profile):
    path = directory / filename
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if (manifest.get("schema") != 1 or manifest.get("profile") != profile
            or manifest.get("dimension") != PROFILES[profile]["dimension"]):
        raise ValueError(f"Incompatible profile manifest: {path}")
    files = manifest.get("files")
    if not isinstance(files, dict) or not files:
        raise ValueError(f"Empty profile manifest: {path}")
    for relative in files:
        item = directory / relative
        if not item.resolve().is_relative_to(directory.resolve()) or not item.is_file():
            raise FileNotFoundError(f"Missing or invalid profile file: {item}")
    return manifest


def profile_available(root, profile, *, require_m4=False):
    directory = root / profile
    try:
        if profile != "prostt5":
            manifest = profile_files(directory, "manifest.json", profile)
            required = {"encoder/model.safetensors", "encoder/config.json", "encoder/vocab.txt", "labels.json",
                        "Struct_prototype_bank.csv", "Non_Struct_prototype_bank.csv",
                        *(f"heads/M{number}.pt" for number in range(1, 7))}
            suffix = "prototype_positions.npy" if manifest["prototypes_from_train"] else "prototypes.npy"
            required.update(f"{branch}_{suffix}" for branch in ("Struct", "Non_Struct"))
            if not required <= manifest["files"].keys():
                return False
            if manifest["prototypes_from_train"]:
                train = profile_files(directory, "train_manifest.json", profile)
                if "train_vectors.npy" not in train["files"]:
                    return False
        if require_m4:
            manifest = profile_files(directory, "m4_manifest.json", profile)
            return {"m4_vectors.npy", "m4_targets.npy", "m4_classes.json"} <= manifest["files"].keys()
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        return False
    return True


def available_profiles():
    root = profile_root()
    return [dict(id=key, **value, installed=profile_available(root, key),
                 faiss=profile_available(root, key, require_m4=True))
            for key, value in PROFILES.items()]


def verify_manifest(directory, filename, profile):
    path = directory / filename
    if not path.is_file():
        raise FileNotFoundError(f"Install {profile} artifacts at {directory} ({filename} missing).")
    manifest = profile_files(directory, filename, profile)
    for relative, expected in manifest["files"].items():
        item = directory / relative
        if sha256(item) != expected:
            raise ValueError(f"Profile checksum mismatch: {item}")
    return manifest
