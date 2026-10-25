"""SystemVerilog language module (ADR-0011), registered as the `systemverilog` entry point."""

from judge.core.registry import LanguageModule
from judge.languages.systemverilog.stages.lint import LintStage
from judge.languages.systemverilog.stages.precheck import PrecheckStage

# sim arrives with T0.9.
LANGUAGE = LanguageModule(
    name="systemverilog",
    stages={stage.stage_type: stage for stage in (PrecheckStage, LintStage)},
)
