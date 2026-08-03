from __future__ import annotations

import re
from pathlib import Path

from oxigraph.commands.index_stats import (
    IndexStatsCommand as OxigraphIndexStatsCommand,
)
from qlever.log import log

TOTAL_ELAPSED_PATTERN = re.compile(r"Total elapsed=(\d+)ms")


class IndexStatsCommand(OxigraphIndexStatsCommand):
    """
    Show how long the index build took and how much space the index uses,
    for a Blazegraph dataset.
    """

    def index_size_patterns(self, args) -> list[str]:
        """The index files to add up for the space report."""
        return ["blazegraph.jnl"]

    def parse_index_durations(
        self, log_file_name: str | Path
    ) -> dict[str, float]:
        """
        How long the build took, in seconds, read from the DataLoader's
        "Total elapsed=<n>ms" line. Empty if the log cannot be read or
        holds no such line.
        """
        try:
            with open(log_file_name, "r") as log_file:
                lines = log_file.readlines()
        except Exception as e:
            log.error(f"Problem reading index log file {log_file_name}: {e}")
            return {}

        for line in lines:
            match = TOTAL_ELAPSED_PATTERN.search(line)
            if match:
                return {"TOTAL time": float(match.group(1)) / 1000}
        return {}
