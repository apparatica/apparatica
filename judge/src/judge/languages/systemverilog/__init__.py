"""SystemVerilog language module (ADR-0011), registered as the `systemverilog` entry point."""

from importlib import resources

from judge.core.registry import LanguageModule
from judge.languages.systemverilog.rules import package_rules
from judge.languages.systemverilog.stages.lint import LintStage
from judge.languages.systemverilog.stages.precheck import PrecheckStage
from judge.languages.systemverilog.stages.sim import SimStage
from judge.languages.systemverilog.stages.synth import SynthStage

LANGUAGE = LanguageModule(
    name="systemverilog",
    stages={stage.stage_type: stage for stage in (PrecheckStage, LintStage, SimStage, SynthStage)},
    template_checks=(PrecheckStage.stage_type,),
    package_template=resources.files(__name__).joinpath("package_template"),
    package_rules=package_rules,
)
