"""SystemVerilog `precheck` (specs/07 §2.1), run inside the sandbox: it parses untrusted code.

A single file on the standard library and pyslang: the `precheck` stage uploads it next to the
solution and `job.json`, runs `python3 precheck_runner.py job.json solution.sv`, and reads back
`result.json` and the canonical text `canonical.sv`. The judge treats both as untrusted.

Steps, each stops the check if it finds something: size limits; preprocessor tokens (lexer, before
parsing, so no directive is ever executed); syntax; canonical text without comments; whitelist of
syntax kinds and rules on top of it; elaboration with resource limits; state size; interface.
"""

import json
import sys
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import pyslang
from pyslang import ast, parsing, syntax

RESULT_VERSION = 1
SOURCE_NAME = "solution.sv"

TK = parsing.TokenKind
SK = syntax.SyntaxKind


def _kind(name: str) -> syntax.SyntaxKind:
    """Raises on a misspelled kind or one that a new slang version removed."""
    return SK.__members__[name]


def _kinds(names: str) -> frozenset[syntax.SyntaxKind]:
    return frozenset(_kind(name) for name in names.split())


# Any of these means the preprocessor would act on the code.
DIRECTIVE_TOKENS = frozenset(
    TK.__members__[name]
    for name in (
        "Directive",
        "MacroPaste",
        "MacroQuote",
        "MacroEscapedQuote",
        "MacroTripleQuote",
        "LineContinuation",
        "IncludeFileName",
    )
)

ALLOWED_SYSTEM_NAMES = frozenset(
    {
        "$clog2", "$bits", "$size", "$left", "$right", "$high", "$low",
        "$signed", "$unsigned", "$countones", "$onehot", "$onehot0", "$display", "$write",
    }
)  # fmt: skip

# The synthesizable subset (specs/07 §2.1 items 3-5). A kind not listed is forbidden, including
# kinds that future slang versions add.
ALLOWED_NODES = _kinds(
    """
    CompilationUnit ModuleDeclaration ModuleHeader ParameterPortList ParameterDeclaration
    ParameterDeclarationStatement TypeAssignment AnsiPortList ImplicitAnsiPort
    VariablePortHeader NetPortHeader DataDeclaration NetDeclaration TypedefDeclaration
    GenvarDeclaration Declarator EqualsValueClause VariableDimension RangeDimensionSpecifier
    LogicType BitType RegType IntType IntegerType ShortIntType LongIntType ByteType
    ImplicitType NamedType EnumType StructType UnionType StructUnionMember ContinuousAssign
    AlwaysBlock AlwaysCombBlock AlwaysFFBlock TimingControlStatement
    EventControlWithExpression ImplicitEventControl ParenthesizedEventExpression
    SignalEventExpression BinaryEventExpression SimpleSequenceExpr SimplePropertyExpr
    GenerateRegion GenerateBlock LoopGenerate IfGenerate CaseGenerate StandardCaseItem
    DefaultCaseItem ElseClause NamedBlockClause FunctionDeclaration FunctionPrototype
    FunctionPortList FunctionPort ReturnStatement SequentialBlockStatement
    ConditionalStatement ConditionalPredicate ConditionalPattern CaseStatement
    ForLoopStatement ForVariableDeclaration ExpressionStatement EmptyStatement JumpStatement
    IdentifierName IdentifierSelectName ScopedName SystemName ElementSelect BitSelect
    SimpleRangeSelect AscendingRangeSelect DescendingRangeSelect InvocationExpression
    ArgumentList OrderedArgument IntegerLiteralExpression IntegerVectorExpression
    UnbasedUnsizedLiteralExpression StringLiteralExpression ParenthesizedExpression
    ConditionalExpression ConcatenationExpression MultipleConcatenationExpression
    CastExpression SignedCastExpression AssignmentPatternExpression SimpleAssignmentPattern
    StructuredAssignmentPattern ReplicatedAssignmentPattern AssignmentPatternItem
    AssignmentExpression NonblockingAssignmentExpression AddAssignmentExpression
    SubtractAssignmentExpression MultiplyAssignmentExpression AndAssignmentExpression
    OrAssignmentExpression XorAssignmentExpression LogicalLeftShiftAssignmentExpression
    LogicalRightShiftAssignmentExpression PostincrementExpression PostdecrementExpression
    UnaryPreincrementExpression UnaryPredecrementExpression UnaryPlusExpression
    UnaryMinusExpression UnaryLogicalNotExpression UnaryBitwiseNotExpression
    UnaryBitwiseAndExpression UnaryBitwiseOrExpression UnaryBitwiseXorExpression
    UnaryBitwiseNandExpression UnaryBitwiseNorExpression UnaryBitwiseXnorExpression
    AddExpression SubtractExpression MultiplyExpression DivideExpression ModExpression
    PowerExpression BinaryAndExpression BinaryOrExpression BinaryXorExpression
    BinaryXnorExpression EqualityExpression InequalityExpression CaseEqualityExpression
    CaseInequalityExpression WildcardEqualityExpression WildcardInequalityExpression
    GreaterThanExpression GreaterThanEqualExpression LessThanExpression
    LessThanEqualExpression LogicalAndExpression LogicalOrExpression
    LogicalShiftLeftExpression LogicalShiftRightExpression ArithmeticShiftLeftExpression
    ArithmeticShiftRightExpression InsideExpression RangeList ValueRangeExpression
    """
)

# Explanations for the forbidden constructs that people actually write; others get a generic one.
_NOT_SYNTHESIZABLE = "не синтезируется"
_ONE_MODULE = "решение — один модуль без вложенных и вспомогательных"
FORBIDDEN_EXPLANATIONS: dict[syntax.SyntaxKind, str] = {
    _kind(name): text
    for names, text in (
        ("InitialBlock", f"блок initial {_NOT_SYNTHESIZABLE}: начальное состояние задаёт сброс"),
        ("FinalBlock", f"блок final {_NOT_SYNTHESIZABLE}"),
        ("AlwaysLatchBlock", "always_latch запрещён: защёлки не допускаются"),
        ("DelayControl", "задержки # не синтезируются"),
        ("ParallelBlockStatement", f"fork/join {_NOT_SYNTHESIZABLE}"),
        ("WaitStatement", f"wait {_NOT_SYNTHESIZABLE}"),
        ("ForeverStatement LoopStatement DoWhileStatement",
         "циклы while, repeat и forever запрещены: используйте for с константными границами"),
        ("HierarchyInstantiation", f"инстанцирование модулей запрещено: {_ONE_MODULE}"),
        ("InterfaceDeclaration PackageDeclaration ProgramDeclaration ClassDeclaration",
         f"запрещено: {_ONE_MODULE}"),
        ("CheckerDeclaration ConfigDeclaration UdpDeclaration BindDirective",
         f"запрещено: {_ONE_MODULE}"),
        ("PackageImportDeclaration", "import запрещён: решение не использует пакеты"),
        ("DPIImport DPIExport", "DPI запрещён"),
        ("AttributeInstance", "атрибуты (* … *) запрещены"),
        ("TaskDeclaration", "задачи (task) запрещены: используйте функции automatic"),
        ("RealType ShortRealType RealTimeType StringType CHandleType EventType",
         f"тип {_NOT_SYNTHESIZABLE}"),
        ("ProceduralForceStatement ProceduralReleaseStatement",
         "force/release не синтезируются"),
        ("ProceduralAssignStatement ProceduralDeassignStatement",
         "процедурные assign/deassign не синтезируются"),
        ("BlockingEventTriggerStatement NonblockingEventTriggerStatement",
         "события -> не синтезируются"),
        ("ImmediateAssertStatement ImmediateAssumeStatement ImmediateCoverStatement",
         "проверки assert/assume/cover в решении запрещены"),
        ("AssertPropertyStatement AssumePropertyStatement CoverPropertyStatement",
         "проверки assert/assume/cover в решении запрещены"),
        ("LetDeclaration", "let запрещён"),
        ("SpecifyBlock", f"specify {_NOT_SYNTHESIZABLE}"),
        ("TimeLiteralExpression", "литералы времени не синтезируются"),
        ("VoidCastedCallStatement", "void'(…) не нужен: разрешённые функции возвращают значение"),
    )
    for name in names.split()
}  # fmt: skip


@dataclass(frozen=True)
class Finding:
    category: str  # forbidden | compile | limit
    code: str
    message: str
    line: int = 1
    col: int = 1
    limit: str | None = None  # with category=limit: size | memory


@dataclass
class Result:
    findings: list[Finding] = field(default_factory=list)
    module: str | None = None
    ports_ok: bool | None = None
    state_bits: int | None = None
    canonical: str | None = None

    def to_json(self) -> dict[str, Any]:
        return {
            "v": RESULT_VERSION,
            "findings": [asdict(f) for f in self.findings],
            "module": self.module,
            "ports_ok": self.ports_ok,
            "state_bits": self.state_bits,
        }


@dataclass(frozen=True)
class Limits:
    max_bytes: int
    max_lines: int
    max_state_bits: int
    max_generate_steps: int
    max_constexpr_steps: int


@dataclass(frozen=True)
class Job:
    top: str
    parameters: list[dict[str, Any]]  # {name, type, default}
    ports: list[dict[str, Any]]  # {name, dir, width, signed}
    limits: Limits

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "Job":
        return cls(data["top"], data["parameters"], data["ports"], Limits(**data["limits"]))


def _location(sm: pyslang.SourceManager, loc: pyslang.SourceLocation) -> tuple[int, int]:
    return sm.getLineNumber(loc), sm.getColumnNumber(loc)


def _diagnostic(sm: pyslang.SourceManager, diag: pyslang.Diagnostic) -> Finding:
    line, col = _location(sm, diag.location)
    report = pyslang.DiagnosticEngine.reportAll(sm, [diag]).strip().splitlines()
    text = report[0].split("error: ", 1)[-1] if report else "error"
    code = str(diag.code).removeprefix("DiagCode(").removesuffix(")")
    return Finding("compile", code, text, line, col)


def _tokens(node: Any) -> list[parsing.Token]:
    tokens: list[parsing.Token] = []

    def visit(obj: Any) -> bool:
        if isinstance(obj, parsing.Token):
            tokens.append(obj)
        return True

    node.visit(visit)
    return tokens


def check_size(code: str, limits: Limits) -> list[Finding]:
    size, lines = len(code.encode()), len(code.splitlines())
    if size > limits.max_bytes:
        message = f"решение занимает {size} байт, допустимо {limits.max_bytes}"
        return [Finding("limit", "CODE_SIZE", message, limit="size")]
    if lines > limits.max_lines:
        message = f"в решении {lines} строк, допустимо {limits.max_lines}"
        return [Finding("limit", "CODE_SIZE", message, limit="size")]
    return []


def scan_directives(code: str) -> list[Finding]:
    """Lex without preprocessing: a directive or macro is forbidden and never executed."""
    sm = pyslang.SourceManager()
    buffer = sm.assignText(SOURCE_NAME, code)
    lexer = parsing.Lexer(buffer, pyslang.BumpAllocator(), pyslang.Diagnostics(), sm)
    findings = []
    while (token := lexer.lex()).kind != TK.EndOfFile:
        if token.kind in DIRECTIVE_TOKENS or token.rawText.startswith("`"):
            line, col = _location(sm, token.location)
            message = (
                f"директивы препроцессора запрещены ({token.rawText}): "
                "вместо макросов используйте localparam"
            )
            findings.append(Finding("forbidden", "PREPROCESSOR", message, line, col))
    return findings


def canonical_text(code: str, tokens: Iterable[parsing.Token]) -> str:
    """The solution without comments, printed from tokens: every comment character becomes a
    space and line breaks stay, so lines and columns of all later diagnostics match the code."""
    out = []
    last_end = 0
    for token in tokens:
        for trivia in token.trivia:
            raw = trivia.getRawText()
            match trivia.kind.name:
                case "Whitespace" | "EndOfLine":
                    out.append(raw)
                case "LineComment" | "BlockComment":
                    out.append("".join(ch if ch == "\n" else " " for ch in raw))
                case other:  # directives were rejected by scan_directives
                    raise AssertionError(f"unexpected trivia {other}")
        out.append(token.rawText)
        if token.rawText:
            last_end = token.range.end.offset
    # The end-of-file token is outside a single-module tree: keep only the trailing line breaks.
    # slang offsets count bytes, not characters.
    out.append("\n" * code.encode()[last_end:].count(b"\n"))
    return "".join(out)


def check_syntax(tree: syntax.SyntaxTree, top: str) -> list[Finding]:
    sm = tree.sourceManager
    root: Any = tree.root
    findings: list[Finding] = []
    reported: set[str] = set()

    def report(category: str, code: str, where: Any, message: str) -> None:
        if message in reported:
            return
        reported.add(message)
        token = where if isinstance(where, parsing.Token) else where.getFirstToken()
        line, col = _location(sm, token.location)
        findings.append(Finding(category, code, message, line, col))

    members = list(root.members) if root.kind == SK.CompilationUnit else [root]
    modules = [m for m in members if m.kind == SK.ModuleDeclaration]
    for member in members:
        if member.kind != SK.ModuleDeclaration and member.kind in ALLOWED_NODES:
            report("forbidden", "OUTSIDE_MODULE", member, "объявления вне модуля запрещены")
    if len(modules) != 1:
        where = modules[1] if len(modules) > 1 else root
        report("compile", "MODULE_COUNT", where, f"в решении должен быть ровно один модуль {top}")
    elif modules[0].header.name.valueText != top:
        report("compile", "MODULE_NAME", modules[0].header.name, f"модуль должен называться {top}")

    def visit(obj: Any) -> bool:
        if isinstance(obj, parsing.Token):
            if obj.kind == TK.SystemIdentifier and obj.valueText not in ALLOWED_SYSTEM_NAMES:
                message = f"системная задача или функция {obj.valueText} запрещена"
                report("forbidden", "SYSTEM_TASK", obj, message)
            elif obj.kind in (TK.DoubleColon, TK.UnitSystemName, TK.RootSystemName):
                message = f"{obj.rawText} запрещён: решение не обращается к пакетам и $root"
                report("forbidden", "SCOPE", obj, message)
            return True
        kind = obj.kind
        if kind not in ALLOWED_NODES:
            explanation = FORBIDDEN_EXPLANATIONS.get(kind, "не входит в синтезируемое подмножество")
            report("forbidden", "CONSTRUCT", obj, f"конструкция {kind.name}: {explanation}")
            return False  # one finding per subtree
        if kind == SK.ModuleDeclaration and obj is not root and obj.parent is not None:
            if obj.parent.kind != SK.CompilationUnit:
                report("forbidden", "CONSTRUCT", obj, f"вложенные модули запрещены: {_ONE_MODULE}")
        elif kind == SK.TimingControlStatement:
            parent = obj.parent.kind if obj.parent is not None else None
            if parent not in (SK.AlwaysBlock, SK.AlwaysFFBlock):
                message = "управление по событию допустимо только в начале always / always_ff"
                report("forbidden", "EVENT_CONTROL", obj, message)
            elif obj.timingControl.kind not in (
                SK.EventControlWithExpression,
                SK.ImplicitEventControl,
            ):
                report("forbidden", "EVENT_CONTROL", obj, "допустимы только @(…) и @*")
        elif kind in (SK.AlwaysBlock, SK.AlwaysFFBlock):
            if obj.statement.kind != SK.TimingControlStatement:
                message = "always / always_ff должен начинаться с @(…)"
                report("forbidden", "EVENT_CONTROL", obj, message)
        elif kind == SK.FunctionDeclaration:
            lifetime = obj.prototype.lifetime
            if lifetime is None or lifetime.kind != TK.AutomaticKeyword:
                message = "функции должны быть automatic"
                report("forbidden", "FUNCTION_LIFETIME", obj, message)
        return True

    root.visit(visit)
    # Forbidden constructs first: they are the answer to "why", structure errors follow from them.
    return sorted(findings, key=lambda f: f.category != "forbidden")


def _literal(value: Any) -> str:
    return str(value) if isinstance(value, int) else f"({value})"


def expected_widths(job: Job) -> tuple[dict[str, int], list[Finding]]:
    """Port widths of problem.yaml evaluated by slang with the default parameter values."""
    lines = ["module __apx_expected;"]
    for param in job.parameters:
        lines.append(
            f"  localparam {param['type']} {param['name']} = {_literal(param['default'])};"
        )
    for index, port in enumerate(job.ports):
        lines.append(f"  localparam longint __apx_w{index} = {port['width']};")
    lines.append("endmodule")
    compilation = ast.Compilation()
    compilation.addSyntaxTree(syntax.SyntaxTree.fromText("\n".join(lines), "expected.sv"))
    if any(d.isError() for d in compilation.getAllDiagnostics()):
        # problem.yaml is the author's: judge validate catches this before publishing.
        return {}, [Finding("compile", "MANIFEST", "ширины портов в problem.yaml не вычисляются")]
    values = {p.name: p.value for p in compilation.getRoot().topInstances[0].body.parameters}
    widths = {
        port["name"]: int(values[f"__apx_w{index}"].value) for index, port in enumerate(job.ports)
    }
    return widths, []


def elaborate(tree: syntax.SyntaxTree, job: Job, result: Result) -> list[Finding]:
    sm = tree.sourceManager
    options = ast.CompilationOptions()
    options.maxGenerateSteps = job.limits.max_generate_steps
    options.maxConstexprSteps = job.limits.max_constexpr_steps
    options.maxInstanceArray = 1024
    options.errorLimit = 20
    options.topModules = {job.top}
    # Interface widths are checked with the problem's default parameters, not the solution's.
    options.paramOverrides = [f"{p['name']}={_literal(p['default'])}" for p in job.parameters]
    compilation = ast.Compilation(pyslang.Bag([options]))
    compilation.addSyntaxTree(tree)
    findings = [_diagnostic(sm, d) for d in compilation.getAllDiagnostics() if d.isError()]
    if findings:
        return findings
    tops = [inst for inst in compilation.getRoot().topInstances if inst.name == job.top]
    if not tops:
        return [Finding("compile", "MODULE_NAME", f"модуль {job.top} не найден")]
    body = tops[0].body
    result.module = job.top

    # Total state: slang accepts huge unpacked arrays that Verilator and Yosys would allocate.
    state_bits = 0

    def count(symbol: Any) -> bool:
        nonlocal state_bits
        if symbol.kind in (ast.SymbolKind.Variable, ast.SymbolKind.Net):
            state_bits += symbol.type.bitstreamWidth
        return True

    body.visit(count)
    result.state_bits = state_bits
    if state_bits > job.limits.max_state_bits:
        line, col = _location(sm, body.location)
        message = (
            f"переменные и цепи решения занимают {state_bits} бит, "
            f"допустимо {job.limits.max_state_bits}"
        )
        return [Finding("limit", "STATE_SIZE", message, line, col, limit="memory")]

    widths, problems = expected_widths(job)
    if problems:
        return problems
    findings += check_interface(body, job, widths, sm)
    result.ports_ok = not findings
    return findings


_DIRECTIONS = {"In": "input", "Out": "output", "InOut": "inout"}


def check_interface(
    body: Any, job: Job, widths: dict[str, int], sm: pyslang.SourceManager
) -> list[Finding]:
    findings = []

    def add(code: str, message: str, where: Any = None) -> None:
        line, col = _location(sm, where.location) if where is not None else (1, 1)
        findings.append(Finding("compile", code, message, line, col))

    actual = {p.name: p for p in body.portList}
    for port in job.ports:
        name = port["name"]
        found = actual.pop(name, None)
        if found is None:
            add("PORT_MISSING", f"нет порта {name}", body)
            continue
        direction = _DIRECTIONS.get(found.direction.name, found.direction.name)
        if direction != port["dir"]:
            add(
                "PORT_DIRECTION",
                f"порт {name}: ожидается {port['dir']}, объявлен {direction}",
                found,
            )
        if found.type.bitWidth != widths[name]:
            message = (
                f"порт {name}: ожидается ширина {port['width']} ({widths[name]}), "
                f"объявлено {found.type.bitWidth}"
            )
            add("PORT_WIDTH", message, found)
        if found.type.isSigned != port["signed"]:
            expected = "знаковый" if port["signed"] else "беззнаковый"
            add("PORT_SIGNED", f"порт {name}: ожидается {expected}", found)
    for name, extra in actual.items():
        add("PORT_EXTRA", f"лишний порт {name}", extra)

    declared = [p.name for p in body.parameters if not p.isLocalParam]
    required = [p["name"] for p in job.parameters]
    for name in required:
        if name not in declared:
            add("PARAM_MISSING", f"нет параметра {name}", body)
    for name in declared:
        if name not in required:
            add("PARAM_EXTRA", f"лишний параметр {name}: используйте localparam", body)
    return findings


def precheck(code: str, job: Job) -> Result:
    result = Result()
    result.findings = check_size(code, job.limits) or scan_directives(code)
    if result.findings:
        return result
    sm = pyslang.SourceManager()
    tree = syntax.SyntaxTree.fromText(code, sm, SOURCE_NAME)
    result.findings = [_diagnostic(sm, d) for d in tree.diagnostics if d.isError()]
    if result.findings:
        return result
    result.canonical = canonical_text(code, _tokens(tree.root))
    result.findings = check_syntax(tree, job.top) or elaborate(tree, job, result)
    return result


def main(argv: list[str]) -> int:
    job_path, solution_path = Path(argv[1]), Path(argv[2])
    job = Job.from_json(json.loads(job_path.read_text(encoding="utf-8")))
    raw = solution_path.read_bytes()
    try:
        result = precheck(raw.decode("utf-8"), job)
    except UnicodeDecodeError as error:
        result = Result([Finding("compile", "ENCODING", f"решение не в UTF-8: байт {error.start}")])
    if result.canonical is not None:
        Path("canonical.sv").write_text(result.canonical, encoding="utf-8", newline="")
    Path("result.json").write_text(json.dumps(result.to_json(), ensure_ascii=False), "utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
