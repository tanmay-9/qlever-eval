from __future__ import annotations

import re

from oxigraph.commands.index_stats import IndexStatsCommand
from qlever.containerize import Containerize
from qlever.resource_usage.usage_plot import (
    UsagePlot as BaseUsagePlot,
)
from qlever.resource_usage.usage_plot import (
    bands_from_durations,
)
from qlever.util import run_command


class UsagePlot(BaseUsagePlot):
    """Resource-usage plot for an Oxigraph index build."""

    def overlay(self) -> list[tuple[str, float, float]]:
        """Shade the load and optimize phases. The log has no timestamps,
        so the phases are assumed to run back to back from the build
        start."""
        return bands_from_durations(
            IndexStatsCommand().parse_index_durations(self.log_path)
        )

    def subtitle(self) -> str | None:
        """Assemble a 'version | read-only' line from the index args."""
        if self.args.system in Containerize.supported_systems():
            version_cmd = (
                f"{self.args.system} run --rm {self.args.image} --version"
            )
        else:
            version_cmd = f"{self.args.index_binary} --version"
        try:
            version_output = run_command(version_cmd, return_output=True)
        except Exception:
            version_output = ""
        version_match = re.search(r"\d+(?:\.\d+)+", version_output)
        parts = []
        if version_match:
            parts.append(f"{self.args.index_binary} v{version_match.group()}")
        parts.append(f"read-only = {self.args.read_only}")
        return "   |   ".join(parts)
