from __future__ import annotations

from blazegraph import BLAZEGRAPH_VERSION
from blazegraph.commands.index_stats import IndexStatsCommand
from qlever.resource_usage.usage_plot import (
    SUBTITLE_SEPARATOR,
    bands_from_durations,
)
from qlever.resource_usage.usage_plot import (
    UsagePlot as BaseUsagePlot,
)


class UsagePlot(BaseUsagePlot):
    """Resource-usage plot for a Blazegraph index build."""

    def overlay(self) -> list[tuple[str, float, float]]:
        """Shade each phase found in the index log. The log has no
        timestamps, so the phases are assumed to run back to back from the
        build start. The DataLoader reports only its total so far, which
        leaves nothing to shade."""
        return bands_from_durations(
            IndexStatsCommand().parse_index_durations(self.log_path)
        )

    def subtitle(self) -> str | None:
        """Assemble a 'version | jvm-args' line. The version is the fixed
        one, since Blazegraph has no way to report it."""
        return SUBTITLE_SEPARATOR.join(
            [
                f"blazegraph v{BLAZEGRAPH_VERSION}",
                f"jvm-args = {self.args.jvm_args}",
            ]
        )
