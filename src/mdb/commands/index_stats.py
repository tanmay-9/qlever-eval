from __future__ import annotations

import re
from pathlib import Path

from qlever.commands.index_stats import (
    IndexStatsCommand as QleverIndexStatsCommand,
)
from qlever.commands.index_stats import (
    get_size_unit,
    get_size_unit_factor,
    get_time_unit,
    get_time_unit_factor,
)
from qlever.log import log
from qlever.util import get_total_file_size

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


def parse_index_durations(log_file_name: str | Path) -> dict[str, float]:
    """
    Parse a MillenniumDB index log and return the duration in seconds of
    each phase, keyed by phase label and in log order. One entry per
    "<label> duration: <value> <unit>" line, with the "total import"
    label normalized to "TOTAL time". Returns {} on error.
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


class IndexStatsCommand(QleverIndexStatsCommand):
    """
    Show index build time and disk space usage for a MillenniumDB dataset.
    Time is parsed from the "duration:" lines in the index log; space is
    the total size of all files in the index directory.
    """

    def execute_time(
        self, args, log_file_name: str
    ) -> dict[str, tuple[float | None, str]]:
        """
        Show the duration of each phase found in the MillenniumDB index log.
        """
        index_durations = parse_index_durations(log_file_name)
        if not index_durations:
            return {}
        time_unit = get_time_unit(
            args.time_unit, max(index_durations.values())
        )
        unit_factor = get_time_unit_factor(time_unit)
        return {
            label: (value_s / unit_factor, time_unit)
            for label, value_s in index_durations.items()
        }

    def execute_space(self, args) -> dict[str, tuple[float, str]]:
        """
        Return the space used by the index files (all files in the index
        directory) along with the unit.
        """
        index_size = get_total_file_size([f"{args.name}_index/*"])

        size_unit = get_size_unit(args.size_unit, index_size)
        unit_factor = get_size_unit_factor(size_unit)

        index_size /= unit_factor

        return {"TOTAL size": (index_size, size_unit)}
