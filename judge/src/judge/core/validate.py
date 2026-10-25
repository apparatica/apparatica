"""`judge validate`: checks of a problem package before it is published (specs/06 §5, FR-PKG-02/03).

The checks run the package through the same pipelines as submissions:

1. `problem.yaml` against the schema and its cross references;
2. the language module, stage plugins and stage configs, stage limits of the resource class;
3. the files the manifest names exist inside the package;
4. the statement is UTF-8 (rendering with KaTeX and WaveDrom is checked from T1.10);
5. the starter template passes the stages the language checks templates with (precheck);
6. every reference solution is `accepted` by the submit pipeline on several seeds — this also
   checks the number of tests per group: the sim stage fails a run whose groups do not match
   `testbenches[].groups`;
7. every mutant gets its `expect` verdict, from a stage in `caught_by` or an earlier one;
8. with `determinism`, the first reference run is repeated with the same seed: stage results and
   artifacts must match byte for byte (FST excepted: its header holds the date).

Seeds are derived from `id@version`, so a run is reproducible with `judge run --seed`.
"""

import hashlib
from collections.abc import Callable, Iterator, Sequence
from contextlib import AbstractContextManager
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from judge.core.events import EventSink
from judge.core.executor import Executor, check_relative
from judge.core.limits import ResourceClasses, stage_limits
from judge.core.package import ManifestError, Problem, load_manifest
from judge.core.pipeline import Job, PipelineConfigError, plan_stages, run_pipeline
from judge.core.registry import LanguageModule, UnknownLanguageError, get_language
from judge.core.stage import StageResult
from judge.core.verdict import Verdict, aggregate

DEFAULT_SEEDS = 3
ExecutorFactory = Callable[[Problem], AbstractContextManager[Executor]]
Artifacts = dict[str, bytes]  # "<stage>/<name>" -> content


@dataclass(frozen=True)
class Check:
    status: Literal["ok", "fail", "skip"]
    what: str
    detail: str = ""


class _NullSink:
    def emit(self, event: object) -> None:
        pass


def validation_seeds(problem: Problem, count: int) -> list[int]:
    """Deterministic 63-bit seeds (the seed column is a signed bigint) for one package version."""
    seeds = []
    for index in range(count):
        digest = hashlib.sha256(f"{problem.id}@{problem.version}#{index}".encode()).digest()
        seeds.append(int.from_bytes(digest[:8], "big") >> 1)
    return seeds


def describe(results: Sequence[StageResult], verdict: Verdict) -> str:
    """One line on why a run got its verdict: stage, test and cycle, the first diagnostic."""
    stage = next((r for r in results if r.status in ("error", "failed")), None)
    if stage is None:
        warnings = [r.key for r in results if r.status == "warning"]
        return f"{verdict.status}" + (
            f" (предупреждения: {', '.join(warnings)})" if warnings else ""
        )
    parts = [f"{verdict.status}: этап {stage.key}"]
    if stage.error_code:
        parts.append(stage.error_code)
    if stage.limit:
        parts.append(f"лимит {stage.limit}")
    if stage.summary.caption:
        parts.append(stage.summary.caption)
    diagnostic = next((d for d in stage.summary.diagnostics if d.severity == "error"), None)
    if diagnostic is not None:
        where = f"{diagnostic.file}:{diagnostic.line}: " if diagnostic.line else ""
        parts.append(f"{where}{diagnostic.message}")
    return " — ".join(parts)


class PackageValidator:
    def __init__(
        self,
        executor_factory: ExecutorFactory,
        resource_classes: ResourceClasses,
        *,
        seeds: int = DEFAULT_SEEDS,
        determinism: bool = False,
        on_check: Callable[[Check], None] | None = None,
        sink_factory: Callable[[str], EventSink] | None = None,
        language_lookup: Callable[[str], LanguageModule] = get_language,
    ) -> None:
        self.executor_factory = executor_factory
        self.resource_classes = resource_classes
        self.seeds = seeds
        self.determinism = determinism
        self.on_check = on_check or (lambda check: None)
        self.sink_factory = sink_factory or (lambda title: _NullSink())
        self.language_lookup = language_lookup

    def validate(self, package_dir: Path) -> list[Check]:
        checks: list[Check] = []
        for check in self._checks(package_dir):
            checks.append(check)
            self.on_check(check)
        return checks

    def _checks(self, package_dir: Path) -> Iterator[Check]:
        try:
            problem = load_manifest(package_dir)
        except ManifestError as error:
            yield Check("fail", "схема problem.yaml", "; ".join(map(str, error.issues)))
            return
        yield Check("ok", "схема problem.yaml")

        try:
            language = self.language_lookup(problem.language)
            for kind in ("run", "submit"):
                for planned in plan_stages(problem, kind, language):
                    stage_limits(
                        problem, planned.key, planned.stage.stage_type, self.resource_classes
                    )
        except (UnknownLanguageError, PipelineConfigError, ValueError) as error:
            yield Check("fail", "этапы и лимиты", str(error))
            return
        yield Check("ok", "этапы и лимиты")

        missing = [
            name for name in _named_files(problem) if not _is_package_file(package_dir, name)
        ]
        if missing:
            yield Check("fail", "файлы пакета", "нет файлов: " + ", ".join(missing))
            return
        yield Check("ok", "файлы пакета")

        yield self._statement(package_dir, problem)
        yield self._template(package_dir, problem, language)
        yield from self._references(package_dir, problem, language)
        yield from self._mutants(package_dir, problem, language)

    def _run(
        self, language: LanguageModule, job: Job, title: str
    ) -> tuple[list[StageResult], Verdict]:
        results, verdict, _ = self._run_keeping(language, job, title)
        return results, verdict

    def _run_keeping(
        self, language: LanguageModule, job: Job, title: str
    ) -> tuple[list[StageResult], Verdict, Artifacts]:
        artifacts: Artifacts = {}

        def keep(stage: str, name: str, data: bytes) -> None:
            artifacts[f"{stage}/{name}"] = data

        with self.executor_factory(job.problem) as executor:
            results = run_pipeline(
                job,
                language,
                executor,
                self.sink_factory(title),
                self.resource_classes,
                on_artifact=keep,
            )
        return results, aggregate(results), artifacts

    def _job(
        self,
        package_dir: Path,
        problem: Problem,
        solution: str,
        seed: int,
        stages: tuple[str, ...] | None = None,
    ) -> Job:
        data = (package_dir / solution).read_bytes()
        return Job(problem, package_dir, "submit", seed, data, stages)

    def _statement(self, package_dir: Path, problem: Problem) -> Check:
        names = [problem.files.statement, *problem.files.statement_i18n.values()]
        for name in names:
            try:
                (package_dir / name).read_text(encoding="utf-8")
            except UnicodeDecodeError:
                return Check("fail", "условие", f"{name}: не UTF-8")
        return Check("skip", "условие", "рендер KaTeX и WaveDrom проверяется с T1.10")

    def _template(self, package_dir: Path, problem: Problem, language: LanguageModule) -> Check:
        what = f"шаблон {problem.files.template}"
        keys = tuple(
            key
            for key in problem.pipelines.practice.submit
            if problem.stages[key].type in language.template_checks
        )
        if not keys:
            return Check("skip", what, "в пайплайне нет этапов проверки шаблона")
        seed = validation_seeds(problem, 1)[0]
        job = self._job(package_dir, problem, problem.files.template, seed, stages=keys)
        results, verdict = self._run(language, job, what)
        if all(r.status in ("passed", "warning") for r in results):
            return Check("ok", what, ", ".join(keys))
        return Check("fail", what, describe(results, verdict))

    def _references(
        self, package_dir: Path, problem: Problem, language: LanguageModule
    ) -> Iterator[Check]:
        solutions = problem.reference.solutions if problem.reference else []
        if not solutions:
            yield Check("fail", "эталоны", "нет эталонного решения (reference.solutions)")
            return
        for solution in solutions:
            for index, seed in enumerate(validation_seeds(problem, self.seeds)):
                what = f"эталон {solution.file}, сид {seed}"
                job = self._job(package_dir, problem, solution.file, seed)
                results, verdict, artifacts = self._run_keeping(language, job, what)
                if verdict.status != "accepted":
                    yield Check("fail", what, describe(results, verdict))
                    continue
                yield Check("ok", what)
                if self.determinism and index == 0:
                    title = f"детерминизм {solution.file}, сид {seed}"
                    again, _, again_artifacts = self._run_keeping(language, job, title)
                    difference = _difference((results, artifacts), (again, again_artifacts))
                    if difference is None:
                        yield Check("ok", title)
                    else:
                        yield Check("fail", title, f"второй прогон отличается: {difference}")

    def _mutants(
        self, package_dir: Path, problem: Problem, language: LanguageModule
    ) -> Iterator[Check]:
        seed = validation_seeds(problem, 1)[0]
        order = list(problem.pipelines.practice.submit)
        for mutant in problem.mutants:
            name = Path(mutant.file).stem
            what = f"мутант {name}"
            job = self._job(package_dir, problem, mutant.file, seed)
            results, verdict = self._run(language, job, what)
            if verdict.status in ("accepted", "accepted_with_warnings"):
                yield Check("fail", what, f"мутант {name} не пойман (ожидался {mutant.expect})")
                continue
            if verdict.status != mutant.expect:
                detail = f"ожидался {mutant.expect}, получено {describe(results, verdict)}"
                yield Check("fail", what, detail)
                continue
            first = verdict.detail.first_failure
            stage = first.stage if first else None
            if not _caught_in_time(stage, mutant.caught_by, order):
                detail = (
                    f"пойман этапом {stage}, а должен — {', '.join(mutant.caught_by)} или раньше"
                )
                yield Check("fail", what, detail)
                continue
            yield Check("ok", what, f"{verdict.status}, этап {stage}")


# Varies between identical runs: wall clock, and the FST header holds the date (ADR-0004).
_TIMING_FIELDS = {"started_at", "duration_ms"}
_UNSTABLE_ARTIFACTS = (".fst",)


def _difference(
    first: tuple[Sequence[StageResult], Artifacts], second: tuple[Sequence[StageResult], Artifacts]
) -> str | None:
    """Where two runs of the same job differ: a stage result or an artifact, byte for byte."""
    (results_a, artifacts_a), (results_b, artifacts_b) = first, second
    if [r.key for r in results_a] != [r.key for r in results_b]:
        return "набор этапов"
    for a, b in zip(results_a, results_b, strict=True):
        if a.model_dump(exclude=_TIMING_FIELDS) != b.model_dump(exclude=_TIMING_FIELDS):
            return f"результат этапа {a.key}"
    names = sorted(
        name
        for name in artifacts_a.keys() | artifacts_b.keys()
        if not name.endswith(_UNSTABLE_ARTIFACTS)
    )
    for name in names:
        if artifacts_a.get(name) != artifacts_b.get(name):
            return f"артефакт {name}"
    return None


def _caught_in_time(stage: str | None, caught_by: Sequence[str], order: Sequence[str]) -> bool:
    """A mutant caught by a listed stage or by one before them in the submit pipeline passes
    (FR-PKG-02): an earlier stage is a stricter catch."""
    if not caught_by:
        return True
    if stage is None:
        return False
    if stage in caught_by:
        return True
    positions = [order.index(key) for key in caught_by if key in order]
    return stage in order and bool(positions) and order.index(stage) < min(positions)


def _named_files(problem: Problem) -> list[str]:
    names = [
        problem.files.statement,
        problem.files.template,
        *problem.files.statement_i18n.values(),
    ]
    for testbench in problem.testbenches:
        names += testbench.sources
    for solution in problem.reference.solutions if problem.reference else []:
        names.append(solution.file)
        if solution.explanation:
            names.append(solution.explanation)
    names += [mutant.file for mutant in problem.mutants]
    return list(dict.fromkeys(names))


def _is_package_file(package_dir: Path, name: str) -> bool:
    try:
        relative = check_relative(name)
    except ValueError:
        return False
    root = package_dir.resolve()
    path = (root / relative).resolve()
    return path.is_relative_to(root) and path.is_file()
