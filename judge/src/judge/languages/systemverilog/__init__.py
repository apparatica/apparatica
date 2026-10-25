"""SystemVerilog language module (ADR-0011), registered as the `systemverilog` entry point."""

from judge.core.registry import LanguageModule
from judge.languages.systemverilog.stages.precheck import PrecheckStage

# lint and sim arrive with T0.8 and T0.9.
LANGUAGE = LanguageModule(
    name="systemverilog",
    stages={stage.stage_type: stage for stage in (PrecheckStage,)},
)
