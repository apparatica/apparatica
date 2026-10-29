"""Pictures of problem statements (FR-PRB-03): the files under `assets/` of a package.

The import puts each picture into the packages bucket next to the package archive, as an object
of its own; the API serves it by problem version. The rules of a picture path are those of the
statement render (web/src/lib/statement/render.ts) and its check in `judge validate`.
"""

from pathlib import PurePosixPath

ASSETS_DIR = "assets"
PICTURES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".svg": "image/svg+xml",
    ".webp": "image/webp",
}


def picture_type(path: str) -> str | None:
    """The media type of a picture of the statement, `assets/…`; None for any other path."""
    parts = path.split("/")
    if (
        len(parts) < 2
        or parts[0] != ASSETS_DIR
        or any(part in ("", ".", "..") for part in parts)
        or any(char in path for char in "?#\\")
    ):
        return None
    return PICTURES.get(PurePosixPath(path).suffix.lower())


def asset_key(slug: str, version: int, content_hash: str, path: str) -> str:
    """Object key in the packages bucket, beside `<slug>/<version>-<hash>.tar.zst`."""
    return f"{slug}/{version}-{content_hash}/{path}"
