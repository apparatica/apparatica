"""Deterministic package archive and `content_hash` (specs/06 §2, §5-6).

`content_hash` is the sha256 of the `sha256sum`-style listing of the package: one line
`<sha256 of file>  <path>` per file, sorted by path, so it can be reproduced with
`find . -type f | sort | xargs sha256sum | sha256sum` (paths without the leading `./`).
The archive is a tar.zst of the same files with fixed metadata: the same package gives the same
bytes, whoever packs it.
"""

import hashlib
import io
import tarfile
from dataclasses import dataclass
from pathlib import Path

import zstandard

ZSTD_LEVEL = 19


class PackError(ValueError):
    pass


@dataclass(frozen=True)
class PackageFile:
    path: str  # relative POSIX path
    data: bytes

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.data).hexdigest()


def _skipped(part: str) -> bool:
    """Editor and VCS litter is not part of a package."""
    return part.startswith(".") or part == "__pycache__"


def package_files(package_dir: Path) -> list[PackageFile]:
    """Regular files of a package, sorted by path. Symlinks are refused: a package is
    self-contained, and a link could point anywhere on the machine that packs it."""
    root = package_dir.resolve()
    files = []
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if any(_skipped(part) for part in relative.parts):
            continue
        if path.is_symlink():
            raise PackError(f"{relative.as_posix()}: symbolic links are not allowed in a package")
        if path.is_file():
            files.append(PackageFile(relative.as_posix(), path.read_bytes()))
    if not files:
        raise PackError(f"{package_dir}: no files")
    return sorted(files, key=lambda f: f.path.encode())


def content_hash(files: list[PackageFile]) -> str:
    listing = "".join(f"{f.sha256}  {f.path}\n" for f in files)
    return hashlib.sha256(listing.encode()).hexdigest()


def pack(files: list[PackageFile]) -> bytes:
    """tar.zst with sorted entries, mode 0644, mtime 0 and no owner names."""
    archive = io.BytesIO()
    with tarfile.open(fileobj=archive, mode="w", format=tarfile.PAX_FORMAT) as tar:
        for file in files:
            info = tarfile.TarInfo(file.path)
            info.size, info.mode, info.mtime = len(file.data), 0o644, 0
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            tar.addfile(info, io.BytesIO(file.data))
    compressor = zstandard.ZstdCompressor(level=ZSTD_LEVEL, write_content_size=True)
    return compressor.compress(archive.getvalue())


def unpack(data: bytes) -> list[PackageFile]:
    """The files of an archive made by `pack` (for checks and tests; members are not extracted
    to disk, so names cannot escape a directory)."""
    raw = zstandard.ZstdDecompressor().decompress(data)
    files = []
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:") as tar:
        for member in tar.getmembers():
            if not member.isfile():
                raise PackError(f"{member.name}: only regular files are allowed")
            extracted = tar.extractfile(member)
            assert extracted is not None
            files.append(PackageFile(member.name, extracted.read()))
    return files
