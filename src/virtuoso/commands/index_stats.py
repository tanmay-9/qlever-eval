from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import NamedTuple

from oxigraph.commands.index_stats import (
    IndexStatsCommand as OxigraphIndexStatsCommand,
)
from qlever import script_name
from qlever.commands.index_stats import (
    get_time_unit,
    get_time_unit_factor,
)
from qlever.log import log

# Line that `index` writes to the log before starting the server, holding
# the settings of the run that follows: "qeval: NumberOfBuffers=340000 ...".
SETTINGS_MARKER_PREFIX = f"{script_name}:"


def write_settings_marker(
    log_file_name: str | Path,
    num_buffers: str,
    max_dirty_buffers: str,
    loaders: int,
    memory_for_buffers: str,
) -> None:
    """
    Append the settings of the running index run to the index log. Neither
    the log nor <name>.virtuoso.ini can be read for them later: Virtuoso
    does not print them, and the ini is rewritten on every run. Call this
    once the server is online, so that the marker falls inside the run.
    """
    with open(log_file_name, "a") as log_file:
        log_file.write(
            f"{SETTINGS_MARKER_PREFIX}"
            f" NumberOfBuffers={num_buffers}"
            f" MaxDirtyBuffers={max_dirty_buffers}"
            f" loaders={loaders}"
            f" memory_for_buffers={memory_for_buffers}\n"
        )


class IndexRun(NamedTuple):
    """
    One completed index run. The settings are None for a run whose marker
    is missing, for example a run indexed before the marker was written.
    """

    duration_s: float
    num_buffers: int | None
    max_dirty_buffers: int | None
    loaders: int | None


def parse_index_runs(log_file_name: str | Path) -> list[IndexRun]:
    """
    Parse the Virtuoso index log and return one entry per completed index
    run, in log order. Returns [] on error or if the log holds no completed
    run.
    """
    try:
        with open(log_file_name, "r") as f:
            lines = f.readlines()
    except Exception as e:
        log.error(f"Problem reading index log file {log_file_name}: {e}")
        return []

    # The log can hold several runs (initial index + extend). A run
    # starts when the server comes online and ends at the first
    # "Checkpoint finished" after the loader is done. Waiting for the
    # loader matters: the server also checkpoints while starting up,
    # before any loading has happened.
    #
    # Date headers ("\t\tMon Feb 16 2026") come before the timestamped
    # lines ("HH:MM:SS ..."), so track the date to handle midnight.
    timestamp_pattern = re.compile(r"^(\d{2}:\d{2}:\d{2})\s")
    date_pattern = re.compile(r"^\t\t\w+ (\w+ \d+ \d{4})")
    IDLE, LOADING, WAITING_CHECKPOINT = range(3)
    state = IDLE
    current_date = None
    start_time = None
    runs = []
    run_settings = {}

    for line in lines:
        date_match = date_pattern.match(line)
        if date_match:
            current_date = datetime.strptime(
                date_match.group(1), "%b %d %Y"
            ).date()
            continue

        # Checked before the timestamps below, which the marker has none of.
        # `index` writes it once the server is online, so it belongs to the
        # run that is open at this point.
        if line.startswith(SETTINGS_MARKER_PREFIX):
            marker = line.removeprefix(SETTINGS_MARKER_PREFIX)
            run_settings = dict(
                setting.split("=", 1)
                for setting in marker.split()
                if "=" in setting
            )
            continue

        ts_match = timestamp_pattern.match(line)
        if not ts_match or current_date is None:
            continue
        ts = datetime.combine(
            current_date,
            datetime.strptime(ts_match.group(1), "%H:%M:%S").time(),
        )

        # "Server online at <isql_port> (pid <pid>)"
        if state == IDLE and "Server online at" in line and "(pid" in line:
            start_time = ts
            run_settings = {}
            state = LOADING
        elif state == LOADING and "Loader has finished" in line:
            state = WAITING_CHECKPOINT
        elif (
            state == WAITING_CHECKPOINT
            and "Checkpoint finished" in line
            and start_time
        ):
            duration = (ts - start_time).total_seconds()
            if duration > 0:
                buffers = run_settings.get("NumberOfBuffers")
                dirty = run_settings.get("MaxDirtyBuffers")
                loaders = run_settings.get("loaders")
                runs.append(
                    IndexRun(
                        duration_s=duration,
                        num_buffers=int(buffers) if buffers else None,
                        max_dirty_buffers=int(dirty) if dirty else None,
                        loaders=int(loaders) if loaders else None,
                    )
                )
            else:
                log.warning(
                    f"Ignoring index run in {log_file_name} that ends "
                    f"at {ts}, before its start at {start_time}"
                )
            state = IDLE

    return runs


class IndexStatsCommand(OxigraphIndexStatsCommand):
    """
    Show how long the index build took and how much space the index uses,
    for a Virtuoso index. Unlike the other engines, the index log is
    timestamped and can hold several runs, so the times are reported per
    run rather than per phase.
    """

    def index_size_patterns(self, args) -> list[str]:
        """The index files to add up for the space report."""
        return ["virtuoso.db"]

    def execute_time(
        self, args, log_file_name: str
    ) -> dict[str, tuple[float | None, str]]:
        """
        Show the duration of each index run found in the Virtuoso index log
        plus their total, all converted to a time unit chosen for the total.
        A run's time includes starting the server and registering the input
        files, not just the loading itself.
        """
        runs = parse_index_runs(log_file_name)
        if not runs:
            return {}
        run_seconds = [run.duration_s for run in runs]

        total_seconds = sum(run_seconds)
        time_unit = get_time_unit(args.time_unit, total_seconds)
        unit_factor = get_time_unit_factor(time_unit)

        stats = {}
        if len(run_seconds) > 1:
            for i, seconds in enumerate(run_seconds):
                stats[f"Index build {i + 1}"] = (
                    seconds / unit_factor,
                    time_unit,
                )
        stats["TOTAL time"] = (total_seconds / unit_factor, time_unit)

        return stats
