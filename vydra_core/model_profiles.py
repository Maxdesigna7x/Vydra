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


def available_profiles():
    root = profile_root()
    return [dict(id=key, **value, installed=key == "prostt5" or (root / key / "manifest.json").is_file(),
                 faiss=(root / key / "m4_manifest.json").is_file())
            for key, value in PROFILES.items()]


def verify_manifest(directory, filename, profile):
    path = directory / filename
    if not path.is_file():
        raise FileNotFoundError(f"Install {profile} artifacts at {directory} ({filename} missing).")
    manifest = json.loads(path.read_text())
    if (manifest.get("schema") != 1 or manifest.get("profile") != profile
            or manifest.get("dimension") != PROFILES[profile]["dimension"]):
        raise ValueError(f"Incompatible profile manifest: {path}")
    files = manifest["files"]
    if not files:
        raise ValueError(f"Empty profile manifest: {path}")
    for relative, expected in files.items():
        item = directory / relative
        if not item.resolve().is_relative_to(directory.resolve()) or sha256(item) != expected:
            raise ValueError(f"Profile checksum mismatch: {item}")
    return manifest
