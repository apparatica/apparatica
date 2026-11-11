"""netlist_sim (specs/07 §2.5): the wrapper of the netlist and the package rules of SV."""

from pathlib import Path
from typing import Any

import pytest

from judge.core.package import Problem, StageConfig, load_manifest
from judge.core.registry import get_language
from judge.languages.systemverilog.rules import package_rules
from judge.languages.systemverilog.stages.netlist import wrapper

FIFO = load_manifest(Path(__file__).parent / "data" / "sync-fifo")


def test_the_wrapper_has_the_interface_and_checks_the_synthesized_parameters() -> None:
    assert wrapper(FIFO, {"WIDTH": "8", "DEPTH": "16"}) == (
        "// Wrapper of netlist_sim: the testbench must use the synthesized parameters.\n"
        "module sync_fifo #(parameter int WIDTH = 8, parameter int DEPTH = 16) (\n"
        "  input logic [(1)-1:0] clk,\n"
        "  input logic [(1)-1:0] rst_n,\n"
        "  input logic [(1)-1:0] push,\n"
        "  input logic [(WIDTH)-1:0] wdata,\n"
        "  input logic [(1)-1:0] pop,\n"
        "  output logic [(WIDTH)-1:0] rdata,\n"
        "  output logic [(1)-1:0] full,\n"
        "  output logic [(1)-1:0] empty\n"
        ");\n"
        "  if (WIDTH != 8) begin : apx_check_WIDTH\n"
        '    $fatal(1, "netlist synthesized for WIDTH=8");\n'
        "  end\n"
        "  if (DEPTH != 16) begin : apx_check_DEPTH\n"
        '    $fatal(1, "netlist synthesized for DEPTH=16");\n'
        "  end\n"
        "  sync_fifo__netlist u (.clk(clk), .rst_n(rst_n), .push(push), .wdata(wdata),"
        " .pop(pop), .rdata(rdata), .full(full), .empty(empty));\n"
        "endmodule\n"
    )


def test_a_wrapper_without_parameters() -> None:
    interface = FIFO.interface.model_copy(
        update={
            "parameters": [],
            "ports": [
                FIFO.interface.ports[0],
                FIFO.interface.ports[5].model_copy(update={"width": "8", "signed": True}),
            ],
        }
    )
    text = wrapper(FIFO.model_copy(update={"interface": interface}), {})
    assert text.splitlines()[1:5] == [
        "module sync_fifo (",
        "  input logic [(1)-1:0] clk,",
        "  output logic signed [(8)-1:0] rdata",
        ");",
    ]
    assert "$fatal" not in text


def with_pipeline(submit: list[str], **stages: dict[str, Any]) -> Problem:
    configs = dict(FIFO.stages) | {k: StageConfig.model_validate(v) for k, v in stages.items()}
    practice = FIFO.pipelines.practice.model_copy(update={"submit": submit})
    return FIFO.model_copy(
        update={
            "stages": configs,
            "pipelines": FIFO.pipelines.model_copy(update={"practice": practice}),
        }
    )


def test_the_rules_are_those_of_the_language_module() -> None:
    assert get_language("systemverilog").package_rules is package_rules
    assert package_rules(FIFO) == []


@pytest.mark.parametrize(
    ("problem", "broken"),
    [
        (
            with_pipeline(["precheck", "sim_full", "synth"]),
            [
                "этап synth: после синтеза нужна симуляция нетлиста — этап"
                " {type: sim, design: synth.netlist_generic} в pipelines.practice.submit"
            ],
        ),
        (
            with_pipeline(["precheck", "netlist_sim", "synth"]),
            [
                "этап netlist_sim: design synth.netlist_generic — нужен netlist_generic этапа"
                " synth, который идёт раньше в pipelines.practice.submit",
                "этап synth: после синтеза нужна симуляция нетлиста — этап"
                " {type: sim, design: synth.netlist_generic} в pipelines.practice.submit",
            ],
        ),
        (
            with_pipeline(
                ["precheck", "synth", "netlist_sim"],
                netlist_sim={"type": "sim", "testbench": "main", "groups": ["public"],
                             "design": "precheck.solution"},
            ),
            [
                "этап netlist_sim: design precheck.solution — нужен netlist_generic этапа"
                " synth, который идёт раньше в pipelines.practice.submit",
                "этап synth: после синтеза нужна симуляция нетлиста — этап"
                " {type: sim, design: synth.netlist_generic} в pipelines.practice.submit",
            ],
        ),
    ],
    ids=["no-netlist-sim", "netlist-sim-before-synth", "design-of-another-stage"],
)  # fmt: skip
def test_every_synth_of_submit_is_followed_by_its_netlist_sim(
    problem: Problem, broken: list[str]
) -> None:
    assert package_rules(problem) == broken


def test_a_run_pipeline_without_synth_cannot_simulate_a_netlist() -> None:
    practice = FIFO.pipelines.practice.model_copy(update={"run": ["precheck", "netlist_sim"]})
    problem = FIFO.model_copy(
        update={"pipelines": FIFO.pipelines.model_copy(update={"practice": practice})}
    )
    assert package_rules(problem) == [
        "этап netlist_sim: design synth.netlist_generic — нужен netlist_generic этапа synth,"
        " который идёт раньше в pipelines.practice.run"
    ]


def test_a_netlist_is_simulated_only_at_the_sets_it_was_synthesized_at() -> None:
    problem = with_pipeline(
        list(FIFO.pipelines.practice.submit),
        synth={"type": "synth", "param_sets": ["wide"]},
    )
    assert package_rules(problem) == [
        "этап netlist_sim: наборы параметров narrow — их нет у этапа synth, нетлист для них"
        " не синтезируется"
    ]


def test_precheck_is_not_expanded_by_parameter_sets() -> None:
    problem = with_pipeline(
        list(FIFO.pipelines.practice.submit), precheck={"type": "precheck", "param_sets": "all"}
    )
    assert package_rules(problem) == [
        "этап precheck: precheck не раскрывается по наборам параметров — он сам сверяет"
        " интерфейс при каждом наборе; уберите param_sets"
    ]


@pytest.mark.parametrize("value", ["8; rm -rf", "WIDTH*2", "8 -p shell"])
def test_the_values_of_a_parameter_set_are_literals(value: str) -> None:
    narrow = FIFO.interface.param_sets[0].model_copy(update={"values": {"WIDTH": value}})
    interface = FIFO.interface.model_copy(
        update={"param_sets": [narrow, *FIFO.interface.param_sets[1:]]}
    )
    problem = FIFO.model_copy(update={"interface": interface})
    assert package_rules(problem) == [
        f"interface.param_sets narrow: WIDTH = {value!r} — не числовой литерал"
    ]


@pytest.mark.parametrize("value", [1, "4'hA", "8'sd3", "1_000"])
def test_number_literals_are_allowed_values(value: int | str) -> None:
    narrow = FIFO.interface.param_sets[0].model_copy(update={"values": {"WIDTH": value}})
    interface = FIFO.interface.model_copy(update={"param_sets": [narrow]})
    assert package_rules(FIFO.model_copy(update={"interface": interface})) == []
