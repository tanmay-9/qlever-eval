from __future__ import annotations

import re
from pathlib import Path

from oxigraph.commands.index_stats import (
    IndexStatsCommand as OxigraphIndexStatsCommand,
)
from qlever.log import log

DURATION_PATTERN = re.compile(
    r"^(.*?)\s*duration:\s*([\d.]+)\s*(milliseconds|seconds|minutes|hours)",
    re.IGNORECASE,
)

UNIT_TO_SECONDS = {
    "milliseconds": 1 / 1000,
    "seconds": 1,
    "minutes": 60,
    "hours": 3600,
}


class IndexStatsCommand(OxigraphIndexStatsCommand):
    """
    Show how long the index build took and how much space the index uses,
    for a MillenniumDB dataset.
    """

    def index_size_patterns(self, args) -> list[str]:
        """The index files to add up for the space report."""
        return [f"{args.name}_index/*"]

    def parse_index_durations(
        self, log_file_name: str | Path
    ) -> dict[str, float]:
        """
        How long each phase of the build took, in seconds, one entry per
        "<label> duration: <value> <unit>" line in the index log and in
        log order. The "total import" label is renamed to "TOTAL time".
        Empty if the log cannot be read.
        """
        try:
            with open(log_file_name, "r") as log_file:
                lines = log_file.readlines()
        except Exception as e:
            log.error(f"Problem reading index log file {log_file_name}: {e}")
            return {}

        durations = {}
        for line in lines:
            match = DURATION_PATTERN.search(line)
            if match is None:
                continue
            label = match.group(1).strip()
            if label.lower() == "total import":
                label = "TOTAL time"
            try:
                value = float(match.group(2))
            except ValueError:
                continue
            durations[label] = value * UNIT_TO_SECONDS[match.group(3).lower()]
        return durations
