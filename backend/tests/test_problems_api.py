"""The problem catalogue API (specs/05 §3) on Postgres with the problems of the repository."""

import shutil
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from apparatica.core.settings import Settings
from apparatica.main import create_app
from conftest import CONFIG_DIR, PROBLEMS, Postgres, import_problems

PUBLIC = "public, max-age=60, stale-while-revalidate=300"
IMMUTABLE = "public, max-age=31536000, immutable"
PROBLEM = "application/problem+json"


def _edit(path: Path, old: str, new: str) -> None:
    content = path.read_bytes()
    assert old.encode() in content
    path.write_bytes(content.replace(old.encode(), new.encode()))


@pytest.fixture(scope="module")
def catalogue(
    postgres: Postgres, catalogue_template: str, tmp_path_factory: pytest.TempPathFactory
) -> str:
    """The five problems published; counter-mod-n v2 published over v1; mux4 v2 imported but
    not published; a problem `draft` imported but never published."""
    root = tmp_path_factory.mktemp("problems")
    for name, slug, number, version in (
        ("counter-mod-n", "counter-mod-n", 2, 2),
        ("mux4", "mux4", 1, 2),
        ("mux4", "draft", 99, 1),
    ):
        copy = root / f"{slug}-{version}" / slug
        shutil.copytree(PROBLEMS / name, copy)
        manifest = copy / "problem.yaml"
        _edit(manifest, f"id: {name}", f"id: {slug}")
        _edit(manifest, "number: 1\n" if name == "mux4" else "number: 2\n", f"number: {number}\n")
        _edit(manifest, "version: 1", f"version: {version}")

    url = postgres.create_database(template=catalogue_template)
    import_problems(url, [root / "counter-mod-n-2" / "counter-mod-n"], publish=True)
    import_problems(url, [root / "mux4-2" / "mux4", root / "draft-1" / "draft"], publish=False)
    return url


@pytest.fixture(scope="module")
def api(catalogue: str) -> Iterator[TestClient]:
    settings = Settings(environment="test", database_url=catalogue, config_dir=CONFIG_DIR)
    with TestClient(create_app(settings), raise_server_exceptions=False) as client:
        yield client


def slugs(api: TestClient, query: str = "") -> list[str]:
    response = api.get(f"/api/v1/problems{query}")
    assert response.status_code == 200, response.text
    return [item["slug"] for item in response.json()["items"]]


def test_tags_in_the_order_of_the_file(api: TestClient) -> None:
    response = api.get("/api/v1/tags")
    assert response.status_code == 200
    assert response.headers["cache-control"] == PUBLIC
    tags = response.json()
    assert [tag["slug"] for tag in tags][:3] == ["combinational", "sequential", "arithmetic"]
    assert {"slug": "fifo", "title": "FIFO"} in tags
    etag = response.headers["etag"]
    assert api.get("/api/v1/tags", headers={"If-None-Match": etag}).status_code == 304


def test_catalogue_lists_published_problems(api: TestClient) -> None:
    response = api.get("/api/v1/problems")
    assert response.status_code == 200
    assert response.headers["cache-control"] == PUBLIC
    body = response.json()
    assert [(item["number"], item["slug"]) for item in body["items"]] == [
        (1, "mux4"),
        (2, "counter-mod-n"),
        (3, "carry-adder"),
        (4, "seq-detector"),
        (5, "sync-fifo"),
    ]
    assert body["items"][0] == {
        "slug": "mux4",
        "number": 1,
        "title": "Мультиплексор 4:1",
        "difficulty": "easy",
        "tags": ["combinational", "multiplexer"],
    }
    assert (body["page"], body["per_page"], body["total"]) == (1, 12, 5)
    assert body["progress"] == [
        {"difficulty": "easy", "total": 3},
        {"difficulty": "medium", "total": 2},
        {"difficulty": "hard", "total": 0},
    ]


def test_catalogue_filters(api: TestClient) -> None:
    assert slugs(api, "?difficulty=medium") == ["seq-detector", "sync-fifo"]
    assert slugs(api, "?difficulty=medium&difficulty=easy&tag=fsm") == ["seq-detector"]
    assert slugs(api, "?tag=fifo&tag=counter") == ["counter-mod-n", "sync-fifo"]
    assert slugs(api, "?tag=no-such-tag") == []
    # The progress summary does not depend on the filters.
    filtered = api.get("/api/v1/problems?difficulty=hard").json()
    assert filtered["total"] == 0
    assert filtered["progress"][0] == {"difficulty": "easy", "total": 3}


@pytest.mark.parametrize(
    ("q", "expected"),
    [
        ("мультиплексор", ["mux4"]),  # the title, whatever the case
        ("СИНХРОННЫЙ", ["sync-fifo"]),
        ("fifo", ["sync-fifo"]),  # a tag slug and the title
        ("счётчики", ["counter-mod-n"]),  # a tag title
        ("  fsm ", ["seq-detector"]),
        ("%", []),  # LIKE wildcards are literal
        ("_", []),
    ],
)
def test_catalogue_search(api: TestClient, q: str, expected: list[str]) -> None:
    assert slugs(api, f"?q={q}") == expected


def test_catalogue_sort_and_pages(api: TestClient) -> None:
    assert slugs(api, "?sort=-number") == [
        "sync-fifo",
        "seq-detector",
        "carry-adder",
        "counter-mod-n",
        "mux4",
    ]
    # By the order of difficulties.yaml, then by number.
    assert slugs(api, "?sort=-difficulty") == [
        "seq-detector",
        "sync-fifo",
        "mux4",
        "counter-mod-n",
        "carry-adder",
    ]
    assert slugs(api, "?sort=difficulty&per_page=2&page=2") == ["carry-adder", "seq-detector"]
    last = api.get("/api/v1/problems?per_page=2&page=3").json()
    assert ([item["slug"] for item in last["items"]], last["total"]) == (["sync-fifo"], 5)
    assert slugs(api, "?page=4&per_page=2") == []


@pytest.mark.parametrize(
    "query", ["?per_page=101", "?per_page=0", "?page=0", "?sort=acceptance", "?q=" + "x" * 101]
)
def test_catalogue_rejects_bad_parameters(api: TestClient, query: str) -> None:
    response = api.get(f"/api/v1/problems{query}")
    assert response.status_code == 422
    assert response.headers["content-type"] == PROBLEM
    assert response.json()["code"] == "VALIDATION_ERROR"


def test_problem_is_its_current_version(api: TestClient) -> None:
    response = api.get("/api/v1/problems/mux4")
    assert response.status_code == 200
    assert response.headers["cache-control"] == PUBLIC
    problem: dict[str, Any] = response.json()
    assert (problem["version"], problem["current_version"]) == (1, 1)  # v2 is not published
    assert problem["title"] == "Мультиплексор 4:1"
    assert problem["language"] == "systemverilog"
    assert problem["resource_class"] == "light"
    assert problem["top"] == "mux4"
    assert problem["statement_md"] == (PROBLEMS / "mux4" / "statement.md").read_text("utf-8")
    assert problem["template"] == (PROBLEMS / "mux4" / "template.sv").read_text("utf-8")
    assert problem["interface"]["parameters"] == [
        {"name": "WIDTH", "type": "int", "default": 8, "description": "Разрядность данных"}
    ]
    assert problem["interface"]["ports"][0] == {
        "name": "sel",
        "dir": "input",
        "width": "2",
        "signed": False,
        "role": "data",
        "reset": None,
        "description": "Номер выбираемого входа",
    }
    assert problem["pipeline"] == {
        "run": [
            {"key": "precheck", "type": "precheck"},
            {"key": "lint", "type": "lint"},
            {"key": "sim_run", "type": "sim"},
        ],
        "submit": [
            {"key": "precheck", "type": "precheck"},
            {"key": "lint", "type": "lint"},
            {"key": "sim_full", "type": "sim"},
        ],
    }
    assert problem["tests"] == {"public": 2, "hidden": 2}
    assert problem["changelog"] is None
    assert problem["published_at"].endswith("Z") or "+00:00" in problem["published_at"]


def test_versions_up_to_the_current_one(api: TestClient) -> None:
    assert api.get("/api/v1/problems/counter-mod-n").json()["version"] == 2
    old = api.get("/api/v1/problems/counter-mod-n/versions/1")
    assert old.status_code == 200
    assert old.headers["cache-control"] == IMMUTABLE
    assert (old.json()["version"], old.json()["current_version"]) == (1, 2)
    etag = old.headers["etag"]
    cached = api.get("/api/v1/problems/counter-mod-n/versions/1", headers={"If-None-Match": etag})
    assert cached.status_code == 304
    assert api.get("/api/v1/problems/counter-mod-n/versions/2").json()["version"] == 2


@pytest.mark.parametrize(
    ("path", "status"),
    [
        ("/problems/no-such-problem", 404),
        ("/problems/draft", 404),  # never published
        ("/problems/draft/versions/1", 404),
        ("/problems/mux4/versions/2", 404),  # imported, newer than the current version
        ("/problems/mux4/versions/3", 404),
        ("/problems/mux4/versions/0", 422),
        ("/problems/Mux_4", 422),
    ],
)
def test_unknown_problems_and_versions(api: TestClient, path: str, status: int) -> None:
    response = api.get(f"/api/v1{path}")
    assert response.status_code == status
    assert response.headers["content-type"] == PROBLEM
    assert response.json()["code"] == ("NOT_FOUND" if status == 404 else "VALIDATION_ERROR")
