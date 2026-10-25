"""SystemVerilog language module (ADR-0011), registered as the `systemverilog` entry point."""

from judge.core.registry import LanguageModule

# Stage plugins arrive with T0.7a (precheck), T0.8 (lint) and T0.9 (sim).
LANGUAGE = LanguageModule(name="systemverilog", stages={})
