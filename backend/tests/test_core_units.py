import asyncio
import hashlib
import shutil
import time
import uuid
from collections.abc import Mapping
from pathlib import Path

import pytest

from apparatica.core.flags import FeatureFlags
from apparatica.core.ids import uuid7
from apparatica.core.platform import ConfigFileError, load_platform_config

CONFIG_DIR = Path(__file__).parents[2] / "config"
LEGAL_TEXTS = Path(__file__).parents[2] / "web" / "content" / "legal"


def test_uuid7_layout_and_order() -> None:
    ids = [uuid7() for _ in range(2000)]
    assert all(i.version == 7 and i.variant == uuid.RFC_4122 for i in ids)
    assert ids == sorted(ids)
    assert len(set(ids)) == len(ids)
    milliseconds = ids[0].int >> 80
    assert abs(milliseconds - time.time() * 1000) < 5_000


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def test_flags_are_cached_for_the_ttl() -> None:
    calls = 0
    value = {"captcha": True}

    async def overrides() -> Mapping[str, bool]:
        nonlocal calls
        calls += 1
        return value

    clock = Clock()
    flags = FeatureFlags(overrides, ttl_s=30, clock=clock)

    async def scenario() -> None:
        assert (await flags.values())["captcha"] is True
        value["captcha"] = False
        clock.now = 29
        assert await flags.enabled("captcha") is True
        clock.now = 30
        assert await flags.enabled("captcha") is False

    asyncio.run(scenario())
    assert calls == 2


def test_flags_ignore_unknown_keys_and_survive_errors() -> None:
    state = {"fail": False}

    async def overrides() -> Mapping[str, bool]:
        if state["fail"]:
            raise ConnectionError("database is down")
        return {"reports": True, "no_such_flag": True}

    clock = Clock()
    flags = FeatureFlags(overrides, ttl_s=1, clock=clock)

    async def scenario() -> None:
        values = await flags.values()
        assert values["reports"] is True
        assert "no_such_flag" not in values
        state["fail"] = True
        clock.now = 5
        assert (await flags.values())["reports"] is True  # the last good values stay
        with pytest.raises(KeyError, match="unknown feature flag"):
            await flags.enabled("no_such_flag")

    asyncio.run(scenario())


def test_platform_config_of_the_repository() -> None:
    config = load_platform_config(CONFIG_DIR)
    assert [d.token for d in config.difficulties] == ["e", "m", "h"]
    assert config.limits.quotas.guest.heavy_per_day == 0


def test_every_change_of_a_legal_text_is_a_decision_on_its_version() -> None:
    """A user accepts an edition of a document (FR-AUTH-06): its text must not change unnoticed."""
    for key, document in load_platform_config(CONFIG_DIR).legal.documents:
        text = (LEGAL_TEXTS / f"{key}.md").read_bytes().replace(b"\r\n", b"\n")
        digest = hashlib.sha256(text).hexdigest()
        assert digest == document.sha256, (
            f"web/content/legal/{key}.md changed. In config/legal.yaml set documents.{key}.sha256:"
            f" {digest}, and a new version (the date of the edition) if the change is one of"
            " substance (docs/legal.md)"
        )


def test_platform_config_errors(tmp_path: Path) -> None:
    with pytest.raises(ConfigFileError, match=r"difficulties\.yaml"):
        load_platform_config(tmp_path)
    (tmp_path / "difficulties.yaml").write_text(
        "- {key: easy, title: Easy, token: e}\n- {key: easy, title: Easy, token: e}\n",
        encoding="utf-8",
    )
    for name in ("catalog.yaml", "limits.yaml", "rate-limits.yaml", "legal.yaml", "rating.yaml"):
        (tmp_path / name).write_text((CONFIG_DIR / name).read_text("utf-8"), "utf-8")
    with pytest.raises(ConfigFileError, match="duplicate keys"):
        load_platform_config(tmp_path)
    (tmp_path / "difficulties.yaml").write_text("- {key: Easy, title: E, token: e}\n", "utf-8")
    with pytest.raises(ConfigFileError, match="key"):
        load_platform_config(tmp_path)
    # The points of the global leaderboard name every level once (FR-LB-05).
    shutil.copy(CONFIG_DIR / "difficulties.yaml", tmp_path / "difficulties.yaml")
    (tmp_path / "rating.yaml").write_text(
        "formula_version: 1\nsolved: {easy: 1, medium: 3}\nplaces: [3, 2, 1]\n", "utf-8"
    )
    with pytest.raises(ConfigFileError, match="every difficulty level"):
        load_platform_config(tmp_path)
