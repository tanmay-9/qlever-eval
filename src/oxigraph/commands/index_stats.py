from __future__ import annotations

import re
from pathlib import Path

from qlever import util
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

PHASE_LABELS = ["Load time", "Optimize time", "TOTAL time"]


def parse_index_durations(log_file_name: str | Path) -> dict[str, float]:
    """
    Parse an Oxigraph index log and return the duration in seconds of each
    phase, keyed by phase label and in log order. The durations are read
    from the lines the index command appends to the log. Returns {} on
    error or if no phase was logged.
    """
    try:
        # The times are always near the end of the log.
        log_text = util.run_command(
            f"tail {log_file_name}", return_output=True
        )
    except Exception as e:
        log.error(f"Problem reading index log file {log_file_name}: {e}")
        return {}

    durations = {}
    for label in PHASE_LABELS:
        match = re.search(rf"{re.escape(label)}:\s*(\d+)s", log_text)
        if match:
            durations[label] = float(match.group(1))
    return durations


class IndexStatsCommand(QleverIndexStatsCommand):
    """
    Show index build time and disk space usage for an Oxigraph dataset.
    Time is read from the "TOTAL time" line appended to the index log
    by the index command; space is the sum of all .sst files.
    """

    def execute_time(
        self, args, log_file_name: str
    ) -> dict[str, tuple[float | None, str]]:
        """
        Show the duration of each phase found in the Oxigraph index log,
        all converted to a time unit chosen for the total time.
        """
        raw_seconds = parse_index_durations(log_file_name)
        if not raw_seconds:
            return {}

        # Pick a time unit based on the total time.
        total_s = raw_seconds.get("TOTAL time")
        time_unit = get_time_unit(args.time_unit, total_s)
        unit_factor = get_time_unit_factor(time_unit)

        stats = {
            name: (seconds / unit_factor, time_unit)
            for name, seconds in raw_seconds.items()
        }

        # If there was no optimize step, Load and TOTAL are identical
        if "Optimize time" not in stats:
            stats.pop("Load time", None)

        return stats

    def execute_space(self, args) -> dict[str, tuple[float, str]]:
        """
        Return the space used by the index files (*.sst) along with the unit.
        """
        index_size = util.get_total_file_size([f"{args.name}_index/*.sst"])

        size_unit = get_size_unit(args.size_unit, index_size)
        unit_factor = get_size_unit_factor(size_unit)

        index_size /= unit_factor

        return {"TOTAL size": (index_size, size_unit)}
