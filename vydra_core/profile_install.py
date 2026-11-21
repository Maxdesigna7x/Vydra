"""Download and install a verified Vydra profile outside the source tree."""
import argparse
import re
import shutil
import io
import sys
import tarfile
import tempfile
from pathlib import Path, PurePosixPath
from urllib.request import urlopen

from model_profiles import PROFILES, profile_available, profile_root, sha256, verify_manifest

RELEASE = "https://github.com/Maxdesigna7x/Vydra/releases/download/model-profiles-m4-v1"
LIMITS_GIB = {"esm2-8m": 2, "esm2-35m": 3, "esm2-150m": 4, "prostt5": 5}


def download(path):
    temporary = path.with_name(path.name + ".part")
    try:
        with urlopen(f"{RELEASE}/{path.name}", timeout=60) as response, temporary.open("wb") as stream:
            length = response.headers.get("Content-Length")
            size = int(length) if length is not None else None
            if size is not None and shutil.disk_usage(path.parent).free <= size:
                raise OSError(f"Not enough download space for {path.name}")
            shutil.copyfileobj(response, stream, length=8 * 2**20)
        if size is not None and temporary.stat().st_size != size:
            raise OSError(f"Incomplete download: {path.name}")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


class SplitArchive(io.RawIOBase):
    def __init__(self, parts):
        self.parts = iter(parts)
        self.stream = None

    def readable(self):
        return True

    def readinto(self, buffer):
        while self.stream is not None or (part := next(self.parts, None)) is not None:
            if self.stream is None:
                self.stream = part.open("rb")
            size = self.stream.readinto(buffer)
            if size:
                return size
            self.stream.close()
            self.stream = None
        return 0

    def close(self):
        if self.stream is not None:
            self.stream.close()
        super().close()


def unpack(parts, staging, profile, max_bytes):
    import zstandard

    decoder = zstandard.ZstdDecompressor()
    with SplitArchive(parts) as source, io.BufferedReader(source) as compressed:
        with decoder.stream_reader(compressed, read_across_frames=True) as archive:
            extracted = 0
            with tarfile.open(fileobj=archive, mode="r|") as files:
                for member in files:
                    relative = PurePosixPath(member.name)
                    if (not relative.parts or relative.parts[0] != profile or ".." in relative.parts
                            or "\\" in member.name or ":" in member.name
                            or not (member.isfile() or member.isdir())):
                        raise ValueError(f"Unexpected archive member: {member.name}")
                    destination = staging.joinpath(*relative.parts)
                    if member.isdir():
                        destination.mkdir(parents=True, exist_ok=True)
                        continue
                    extracted += member.size
                    if extracted > max_bytes:
                        raise ValueError("Archive exceeds the published size limit")
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    with files.extractfile(member) as item, destination.open("xb") as target:
                        shutil.copyfileobj(item, target, length=8 * 2**20)
            while archive.read(65536):
                pass


def install_archive(profile, root, parts, limit):
    with tempfile.TemporaryDirectory(dir=root) as temp:
        staging = Path(temp)
        unpack(parts, staging, profile, limit)
        package = staging / profile
        if profile != "prostt5":
            verify_manifest(package, "manifest.json", profile)
        verify_manifest(package, "m4_manifest.json", profile)
        if not profile_available(staging, profile, require_m4=True):
            raise ValueError(f"Required files are missing from the {profile} profile.")
        package.rename(root / profile)
    print(f"Installed {profile}: {root / profile}", flush=True)


def install(profile, root, downloads, local_only):
    root.mkdir(parents=True, exist_ok=True)
    downloads.mkdir(parents=True, exist_ok=True)
    destination = root / profile
    if destination.exists():
        raise FileExistsError(f"Profile already exists at {destination}")
    limit = LIMITS_GIB[profile] * 2**30
    if shutil.disk_usage(root).free < limit:
        raise OSError(f"Allow at least {LIMITS_GIB[profile]} GiB free for installation at {root}")
    sums = downloads / f"{profile}.SHA256SUMS"
    if not sums.is_file() and not local_only:
        download(sums)
    entries = []
    for line in sums.read_text().splitlines():
        checksum, filename = line.split()
        if (not re.fullmatch(r"[a-f0-9]{64}", checksum)
                or not re.fullmatch(re.escape(profile) + r"\.tar\.zst\.part-\d{2}", filename)):
            raise ValueError(f"Invalid checksum entry: {line}")
        entries.append((filename, checksum))
    expected = [f"{profile}.tar.zst.part-{index:02d}" for index in range(len(entries))]
    if not entries or sorted(name for name, _ in entries) != expected:
        raise ValueError("Missing or duplicate profile parts")
    parts = []
    for filename, checksum in sorted(entries):
        part = downloads / filename
        if not part.is_file() and not local_only:
            print(f"Downloading {filename}", flush=True)
            download(part)
        if sha256(part) != checksum:
            raise ValueError(f"Checksum mismatch for {part}")
        parts.append(part)
    if shutil.disk_usage(root).free < limit:
        raise OSError(f"Insufficient installation space after downloads. Move downloads to another disk.")
    install_archive(profile, root, parts, limit)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("profile", choices=tuple(PROFILES))
    parser.add_argument("--root", type=Path, default=profile_root())
    parser.add_argument("--downloads", type=Path, default=Path.home() / ".cache/vydra/profile-downloads")
    parser.add_argument("--local-only", action="store_true", help="Use previously downloaded files")
    args = parser.parse_args()
    try:
        install(args.profile, args.root.expanduser(), args.downloads.expanduser(), args.local_only)
    except (OSError, ValueError, RuntimeError, ImportError, tarfile.TarError) as error:
        sys.exit(str(error))


if __name__ == "__main__":
    main()
