from __future__ import annotations

from blazegraph import BLAZEGRAPH_VERSION
from qlever.resource_usage.usage_plot import SUBTITLE_SEPARATOR
from qlever.resource_usage.usage_plot import (
    UsagePlot as BaseUsagePlot,
)


class UsagePlot(BaseUsagePlot):
    """Resource-usage plot for a Blazegraph index build."""

    def overlay(self) -> list[tuple[str, float, float]]:
        """No phase bands: the DataLoader reports a single cumulative total
        and no phases, so there is nothing to shade. Overridden because the
        base implementation expects QLever's timestamped log."""
        return []

    def subtitle(self) -> str | None:
        """Assemble a 'version | jvm-args' line. The version is the fixed
        one, since Blazegraph has no way to report it."""
        return SUBTITLE_SEPARATOR.join(
            [
                f"blazegraph v{BLAZEGRAPH_VERSION}",
                f"jvm-args = {self.args.jvm_args}",
            ]
        )
