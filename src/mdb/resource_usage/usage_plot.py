from __future__ import annotations

import re

from mdb.commands.index_stats import parse_index_durations
from qlever.containerize import Containerize
from qlever.resource_usage.usage_plot import (
    UsagePlot as BaseUsagePlot,
)
from qlever.resource_usage.usage_plot import (
    bands_from_durations,
)
from qlever.util import run_command


class UsagePlot(BaseUsagePlot):
    """Resource-usage plot for a MillenniumDB index build."""

    def overlay(self) -> list[tuple[str, float, float]]:
        """Shade each phase from the index log's "duration:" lines. The log
        has no timestamps, so the phases are assumed to run back to back
        from the build start."""
        return bands_from_durations(parse_index_durations(self.log_path))

    def subtitle(self) -> str | None:
        """Assemble a 'version | btree' line from the index args."""
        # MillenniumDB has no `--version`; `mdb --help` prints the version
        # as its first line, for example "MillenniumDB v1.0.0".
        if self.args.system in Containerize.supported_systems():
            version_cmd = (
                f"{self.args.system} run --rm {self.args.image} --help"
            )
        else:
            version_cmd = f"{self.args.index_binary} --help"
        try:
            help_output = run_command(version_cmd, return_output=True)
        except Exception:
            help_output = ""
        version_match = re.search(r"\d+(?:\.\d+)+", help_output)
        parts = []
        if version_match:
            parts.append(f"{self.args.index_binary} v{version_match.group()}")
        parts.append(f"buffer-strings = {self.args.buffer_strings}")
        parts.append(f"buffer-tensors = {self.args.buffer_tensors}")
        return "   |   ".join(parts)
