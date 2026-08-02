from __future__ import annotations

import re
from pathlib import Path

from qlever.resource_usage.usage_plot import (
    SUBTITLE_SEPARATOR,
    bands_from_durations,
)
from qlever.resource_usage.usage_plot import (
    UsagePlot as BaseUsagePlot,
)
from virtuoso.commands.index_stats import parse_index_runs


def parse_virtuoso_version(log_path: str | Path) -> tuple[str, str] | None:
    """
    Read version and build hash from the last startup banner in the index
    log, for example "Version 07.20.3243-pthreads for Linux as of May  7
    2026 (c4fd28e38e)". None if the log has no banner.
    """
    pattern = re.compile(r"Version (\d+(?:\.\d+)*)\S*.*\(([0-9a-f]+)\)")
    version = None
    try:
        with open(log_path, "r") as log_file:
            for line in log_file:
                match = pattern.search(line)
                if match:
                    version = (match.group(1), match.group(2))
    except Exception:
        return None
    return version


def shortened_count_str(value: int | None) -> str:
    """Shorten a buffer count for the subtitle, "?" if it is unknown."""
    if value is None:
        return "?"
    if value >= 1_000_000:
        return f"{value / 1_000_000:g}M"
    if value >= 1_000:
        return f"{value / 1_000:g}K"
    return str(value)


class UsagePlot(BaseUsagePlot):
    """Resource-usage plot for a Virtuoso index build."""

    def overlay(self) -> list[tuple[str, float, float]]:
        """Shade one band per index run, numbered as in `index-stats`. The
        runs are laid out back to back, which is what the samples do too:
        their elapsed_s is cumulative over runs and excludes the time
        between them. A single run is left unshaded, since one band over
        the whole figure says nothing."""
        runs = parse_index_runs(self.log_path)
        if len(runs) < 2:
            return []
        return bands_from_durations(
            {
                f"Index build {number}": run.duration_s
                for number, run in enumerate(runs, 1)
            }
        )

    def subtitle(self) -> str | None:
        """Assemble a 'version | buffers | dirty | loaders | runs' line.
        The settings are listed per run, in the order the bands are drawn,
        because the monitored process is the server: its RSS is dominated
        by the buffer pool, so the curve plateaus near NumberOfBuffers
        instead of following the load."""
        parts = []
        version = parse_virtuoso_version(self.log_path)
        if version:
            parts.append(
                f"{self.args.server_binary} v{version[0]} ({version[1]})"
            )
        runs = parse_index_runs(self.log_path)
        if runs:
            buffers = [shortened_count_str(run.num_buffers) for run in runs]
            dirty = [
                shortened_count_str(run.max_dirty_buffers) for run in runs
            ]
            loaders = [
                "?" if run.loaders is None else str(run.loaders)
                for run in runs
            ]
            parts.append(f"buffers = {' · '.join(buffers)}")
            parts.append(f"dirty = {' · '.join(dirty)}")
            parts.append(f"loaders = {' · '.join(loaders)}")
        if len(runs) > 1:
            parts.append(f"{len(runs)} runs")
        return SUBTITLE_SEPARATOR.join(parts) if parts else None
