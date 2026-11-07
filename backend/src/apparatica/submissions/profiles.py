"""Toolchain profiles (specs/09 §2): one sandbox image with fixed tool versions per row.

A profile is immutable like the image tag it names: the same id with other data is refused.
New submissions of a language are checked with its default profile.
"""

from dataclasses import dataclass
from typing import Literal

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from apparatica.submissions.models import ToolchainProfile

PROFILE_KEY = "TOOLCHAIN_PROFILE"
VERSION_SUFFIX = "_VERSION"
LIBERTY_SUFFIX = "_LIB_SHA256"


class ProfileRefusedError(Exception):
    pass


def _entries(versions_lock: str) -> dict[str, str]:
    """`toolchain/versions.lock`: `KEY=value` lines and `#` comments."""
    entries = {}
    for line in versions_lock.splitlines():
        key, sep, value = line.strip().partition("=")
        if sep and not key.startswith("#"):
            entries[key] = value.strip()
    return entries


def tool_versions(versions_lock: str) -> dict[str, str]:
    """`toolchain/versions.lock` → `{"verilator": "5.052", ...}` from its `*_VERSION` keys."""
    tools = {
        key.removesuffix(VERSION_SUFFIX).lower(): value
        for key, value in _entries(versions_lock).items()
        if key.endswith(VERSION_SUFFIX)
    }
    if not tools:
        raise ProfileRefusedError("versions.lock lists no *_VERSION keys")
    return tools


def liberty(versions_lock: str) -> str | None:
    """The synthesis library of the image by its `<NAME>_LIB_SHA256` key: `NANGATE45_LIB_SHA256`
    → `nangate45`, the name the `synth` stage puts into `synth/v1` metrics. None: no synthesis."""
    names = [
        key.removesuffix(LIBERTY_SUFFIX).lower()
        for key in _entries(versions_lock)
        if key.endswith(LIBERTY_SUFFIX)
    ]
    if len(names) > 1:
        raise ProfileRefusedError(f"versions.lock lists more than one liberty: {', '.join(names)}")
    return names[0] if names else None


@dataclass(frozen=True)
class ProfileSpec:
    id: str
    language: str
    image: str
    image_digest: str
    tools: dict[str, str]
    normalization_version: int
    waveview: str | None = None  # the version of the waveview site (waveview/versions.lock)
    liberty: str | None = None  # the synthesis library: synth metrics compare within one only


async def add_profile(
    session: AsyncSession, spec: ProfileSpec, *, default: bool
) -> Literal["created", "unchanged"]:
    if not spec.image_digest.startswith("sha256:"):
        raise ProfileRefusedError(
            f"the image digest must be sha256:<hex>, not {spec.image_digest!r}"
        )
    existing = await session.get(ToolchainProfile, spec.id, with_for_update=True)
    if existing is None:
        outcome: Literal["created", "unchanged"] = "created"
        existing = ToolchainProfile(
            id=spec.id,
            language=spec.language,
            image=spec.image,
            image_digest=spec.image_digest,
            tools=spec.tools,
            normalization_version=spec.normalization_version,
            waveview=spec.waveview,
            liberty=spec.liberty,
        )
        session.add(existing)
        await session.flush()
    else:
        stored = ProfileSpec(
            id=existing.id,
            language=existing.language,
            image=existing.image,
            image_digest=existing.image_digest,
            tools=existing.tools,
            normalization_version=existing.normalization_version,
            waveview=existing.waveview,
            liberty=existing.liberty,
        )
        if stored != spec:
            raise ProfileRefusedError(
                f"profile {spec.id!r} exists with other data; a profile is immutable, add a new one"
            )
        outcome = "unchanged"
    if default and not existing.is_default:
        await session.execute(
            update(ToolchainProfile)
            .where(ToolchainProfile.language == spec.language, ToolchainProfile.is_default)
            .values(is_default=False)
        )
        await session.flush()  # the partial unique index allows one default per language
        existing.is_default = True
        await session.flush()
    return outcome
