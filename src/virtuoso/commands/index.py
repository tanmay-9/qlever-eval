from __future__ import annotations

import re
import shutil
import time
from contextlib import nullcontext
from pathlib import Path

import qlever.util as util
from qlever import script_name
from qlever.command import QleverCommand
from qlever.containerize import Containerize
from qlever.log import log
from qlever.resource_usage.resource_monitor import ResourceMonitor
from virtuoso.commands.index_stats import write_settings_marker
from virtuoso.commands.stop import StopCommand
from virtuoso.resource_usage.usage_plot import UsagePlot

# Virtuoso buffer tuning constants (per GB of free memory)
NUM_BUFFERS_PER_GB = 85_000
MAX_DIRTY_BUFFERS_PER_GB = 65_000

# How long to wait for the server started for loading to come online.
SERVER_STARTUP_TIMEOUT_S = 60


def find_virtuoso_pid(lck_path: Path) -> int | None:
    """
    Read virtuoso.lck and return the PID of the running Virtuoso
    server. The file is written by virtuoso-t on startup and contains
    a ``VIRT_PID=<pid>`` entry.
    """
    try:
        content = lck_path.read_text()
    except OSError:
        return None
    match = re.search(r"VIRT_PID\s*=\s*(\d+)", content)
    return int(match.group(1)) if match else None


def update_virtuoso_ini(
    arg_name: str,
    config_dict: dict[str, dict[str, tuple[str, bool]]],
) -> bool:
    """
    Read the virtuoso.ini file, apply the updates from config_dict,
    and write it back.
    """
    ini_path = Path(f"{arg_name}.virtuoso.ini")
    try:
        lines = ini_path.read_text().splitlines()
        result = util.update_ini_values(lines, config_dict)
        ini_path.write_text("\n".join(result) + "\n")
        return True
    except Exception as e:
        log.error(f"Couldn't update {arg_name}.virtuoso.ini: {e}")
        return False


def log_virtuoso_ini_changes(
    arg_name: str,
    config_dict: dict[str, dict[str, tuple[str, bool]]],
):
    """
    Log the section/option values that will be written to virtuoso.ini.
    Called before execution so the user can review what will change.
    """
    log.info(
        f"Following options of {arg_name}.virtuoso.ini will be updated "
        "with the values from Qleverfile:\n"
    )
    for section, option_dict in config_dict.items():
        log_values = [f"[{section}]"]
        for option, (new_value, _) in option_dict.items():
            log_values.append(f"{option}  =  {new_value}")
        log.info("\n".join(log_values))
        log.info("")


def virtuoso_ini_to_update(args) -> Path | None:
    """
    The .ini file that index and start will write their settings to:
    <name>.virtuoso.ini, or the sole .ini file that would be renamed to
    it. None if there is no such file.
    """
    ini_path = Path(f"{args.name}.virtuoso.ini")
    if ini_path.exists():
        return ini_path
    ini_files = list(Path(".").glob("*.ini"))
    return ini_files[0] if len(ini_files) == 1 else None


def virtuoso_ini_missing_msg(args) -> str:
    """
    Message for a missing <name>.virtuoso.ini, with a hint that depends on
    how many .ini files are there instead: none (suggest setup-config),
    exactly one (will be renamed), or several (ambiguous).
    """
    ini_files = [str(ini) for ini in Path(".").glob("*.ini")]
    if len(ini_files) == 1:
        hint = (
            f"{ini_files[0]} would be renamed to "
            f"{args.name}.virtuoso.ini and used as the config file."
        )
    elif len(ini_files) > 1:
        hint = (
            "More than 1 .ini files found in the current "
            f"directory: {ini_files}\n"
            f"Make sure to only have a unique {args.name}.virtuoso.ini!"
        )
    else:
        hint = (
            "No .ini config file present. Did you call "
            f"`{script_name} {args.engine} setup-config`?"
        )
    return (
        f"{args.name}.virtuoso.ini config file not found in the current "
        f"directory! {hint}"
    )


def resolve_virtuoso_ini(args) -> bool:
    """
    Make sure <name>.virtuoso.ini exists, renaming the sole .ini file in
    the current directory to it if needed. False if that is not possible.
    """
    ini_path = Path(f"{args.name}.virtuoso.ini")
    ini_to_update = virtuoso_ini_to_update(args)
    if ini_to_update is None:
        log.error(virtuoso_ini_missing_msg(args))
        return False
    if ini_to_update != ini_path:
        ini_to_update.rename(ini_path)
        log.info(f"{ini_to_update} renamed to {ini_path}!")
    return True


def index_ini_config(args) -> dict[str, dict[str, tuple[str, bool]]]:
    """
    The virtuoso.ini sections and options that `index` needs to update.
    Each value is a (new_value, is_suffix) tuple.
    """
    http_port = (
        str(args.port)
        if args.system in Containerize.supported_systems()
        else f"{args.host_name}:{args.port}"
    )
    # `parse_memory` guarantees the `<int>G` shape, so this cannot raise.
    memory_for_buffers_gb = int(args.memory_for_buffers[:-1])

    return {
        "Parameters": {
            "ServerPort": (str(args.isql_port), False),
            "NumberOfBuffers": (
                str(NUM_BUFFERS_PER_GB * memory_for_buffers_gb),
                False,
            ),
            "MaxDirtyBuffers": (
                str(MAX_DIRTY_BUFFERS_PER_GB * memory_for_buffers_gb),
                False,
            ),
        },
        "HTTPServer": {
            "ServerPort": (http_port, False),
        },
        "Database": {
            "ErrorLogFile": (f"{args.name}.index-log.txt", False),
        },
    }


def wrap_cmd_in_container(
    args,
    start_cmd: str,
    ld_dir_cmd: str,
    run_cmds: list[str],
    separator: str,
) -> tuple[str, str, str]:
    """
    Wrap the three indexing phases (start server, register files, load
    data) into container commands. The server runs detached, while
    ld_dir and rdf_loader_run are executed via `docker exec`, joined by
    the same separator as in the native case.

    No `working_directory` is needed: the Virtuoso image already has
    /database as its working directory, which is where the current
    directory is mounted, so relative paths resolve into the mount.
    """
    start_cmd = Containerize().containerize_command(
        cmd=f"{start_cmd} -f",
        container_system=args.system,
        run_subcommand="run -d -e DBA_PASSWORD=dba --group-add virtuoso",
        image_name=args.image,
        container_name=args.index_container,
        volumes=[("$(pwd)", "/database")],
        ports=[(args.port, args.port)],
        use_bash=True,
    )
    exec_cmd = f"{args.system} exec {args.index_container}"

    ld_dir_cmd = f"{exec_cmd} {ld_dir_cmd}"
    run_cmd = f'{exec_cmd} bash -c "{separator.join(run_cmds)}"'

    return start_cmd, ld_dir_cmd, run_cmd


class IndexCommand(QleverCommand):
    """
    Build a Virtuoso index for an RDF dataset. The indexing workflow is:
    1. Update virtuoso.ini with Qleverfile settings (ports, memory buffers)
    2. Start the Virtuoso server (virtuoso-t)
    3. Register input files via isql ld_dir()
    4. Load data via rdf_loader_run() (optionally with parallel loaders)
    5. Checkpoint and stop the server
    """

    def __init__(self):
        pass

    def description(self) -> str:
        return "Build the index for a given RDF dataset"

    def should_have_qleverfile(self) -> bool:
        return True

    def relevant_qleverfile_arguments(self) -> dict[str, list[str]]:
        return {
            "data": ["name"],
            "index": [
                "input_files",
                "index_binary",
                "isql_port",
                "num_parallel_loaders",
                "memory_for_buffers",
                "resource_usage_interval",
                "resource_usage_plot_max_points",
            ],
            "server": ["host_name", "port", "server_binary"],
            "runtime": ["system", "image", "index_container"],
        }

    def additional_arguments(self, subparser):
        subparser.add_argument(
            "--extend-existing-index",
            action="store_true",
            default=False,
            help=(
                "Continue loading into the existing virtuoso.db "
                "with new input files. This option can be used to "
                "incrementally load data (with checkpoints) for very "
                "large datasets to prevent total data loss in case of failure."
            ),
        )
        subparser.add_argument(
            "--resource-usage-plot-only",
            action="store_true",
            default=False,
            help="Only render the resource-usage plot from the existing "
            "`<name>.index.resource-usage-log.tsv`; do not build the index. "
            "Use to re-render with a different "
            "`--resource-usage-plot-max-points`",
        )

    def execute(self, args) -> bool:
        # Render the resource-usage plot from the existing log without
        # rebuilding the index.
        if args.resource_usage_plot_only:
            plot_path = UsagePlot(args).render()
            if plot_path is None:
                return False
            log.info(f"Resource-usage plot saved to `{plot_path.name}`")
            return True

        num_parallel_loaders = args.num_parallel_loaders
        start_cmd = f"{args.server_binary} -c {args.name}.virtuoso.ini"

        isql_cmd = f"{args.index_binary} {args.isql_port} dba dba"
        ld_dir_stmts = " ".join(
            f"ld_dir('.', '{f}', '');" for f in args.input_files.split()
        )
        ld_dir_cmd = isql_cmd + f' exec="{ld_dir_stmts}"'

        # Multiple parallel loaders i.e. rdf_loader_run()
        if num_parallel_loaders > 1:
            run_cmds = [
                f"{isql_cmd} exec='rdf_loader_run();' &"
            ] * num_parallel_loaders
            run_cmds.append("wait;")
        else:
            run_cmds = [f"{isql_cmd} exec='rdf_loader_run();'"]

        run_cmds.append(f"{isql_cmd} exec='checkpoint;'")

        separator = " " if num_parallel_loaders > 1 else "; "
        run_cmd = separator.join(run_cmds)

        run_cmd_to_show = "\n".join(run_cmds)
        if args.system in Containerize.supported_systems():
            start_cmd, ld_dir_cmd, run_cmd = wrap_cmd_in_container(
                args, start_cmd, ld_dir_cmd, run_cmds, separator
            )
            run_cmd_to_show = run_cmd

        if args.show and not Path(f"{args.name}.virtuoso.ini").exists():
            self.show(virtuoso_ini_missing_msg(args))

        virtuoso_ini_config_dict = index_ini_config(args)
        if virtuoso_ini_to_update(args) is not None:
            log_virtuoso_ini_changes(args.name, virtuoso_ini_config_dict)

        cmd_to_show = f"{start_cmd}\n\n{ld_dir_cmd}\n{run_cmd_to_show}"

        # Show the command line.
        self.show(cmd_to_show, only_show=args.show)
        if args.show:
            return True

        # Check if all of the input files exist.
        if not util.input_files_exist(args.input_files, args.engine):
            return False

        if args.system in Containerize.supported_systems():
            if Containerize().is_running(args.system, args.index_container):
                log.info(
                    f"{args.system} container {args.index_container} is still up, "
                    "which means that data loading is in progress. Please wait..."
                )
                return False
        else:
            # When running natively, check if the binary exists and works.
            # We use shutil.which instead of util.binary_exists because
            # isql --help writes to stderr instead of stdout
            for binary, ps in [
                (args.index_binary, "index"),
                (args.server_binary, "server"),
            ]:
                if not shutil.which(binary):
                    log.error(
                        f'Running "{binary}" failed, '
                        f"set `--{ps}-binary` to a different binary or "
                        "set `--system to a container system`"
                    )
                    return False

        # Check if previous index exists and user is not trying to extend it
        if Path("virtuoso.db").exists() and not args.extend_existing_index:
            log.error(
                "virtuoso.db found in current directory "
                "which shows presence of a previous index"
            )
            log.info("")
            log.info(
                "Aborting the index operation as --extend-existing-index "
                "option not passed!"
            )
            return False

        # Loading needs its own server, so the database must not be served
        # by another one. This is most likely to happen with
        # --extend-existing-index.
        endpoint_url = f"http://{args.host_name}:{args.port}/sparql"
        if util.is_server_alive(endpoint_url):
            log.error(
                f"Virtuoso server for {args.name} is already running on "
                f"{endpoint_url}\n"
            )
            log.info(
                "Stop it with "
                f"`{script_name} {args.engine} stop` before indexing"
            )
            return False

        if args.system not in Containerize.supported_systems():
            if util.is_port_used(args.isql_port):
                log.error(
                    f"The isql port {args.isql_port} is already used! "
                    "Please specify a different isql_port either as --isql-port "
                    "or in the Qleverfile"
                )
                return False

        if not resolve_virtuoso_ini(args):
            return False

        if not update_virtuoso_ini(args.name, virtuoso_ini_config_dict):
            return False

        # Helper to stop the server/container after a failure so it does
        # not block the next indexing attempt.
        def stop_server():
            try:
                args.server_container = args.index_container
                args.cmdline_regex = StopCommand.DEFAULT_REGEX
                StopCommand().execute(args)
            except Exception as stop_err:
                log.warning(f"Failed to stop Virtuoso server: {stop_err}")

        # The process that tails the index log, terminated in the `finally`
        # below so that it does not outlive a failed index.
        log_proc = None

        # Run the index command.
        try:
            # Delete any existing old log files for a fresh index so that the
            # index time computation is not affected
            if not args.extend_existing_index:
                Path(f"{args.name}.index-log.txt").unlink(missing_ok=True)
            # Run the index container in detached mode
            util.run_command(start_cmd)
            log.info("Waiting for Virtuoso server to be online...")
            start_time = time.time()
            log_file = Path(f"{args.name}.index-log.txt")
            # Wait until the Virtuoso server is online, and start tailing
            # the index log file as soon as it exists (note that the `exec`
            # is important to make sure that the tail process is killed and
            # not just the bash process).
            while not util.is_server_alive(endpoint_url):
                if time.time() - start_time > SERVER_STARTUP_TIMEOUT_S:
                    log.error(
                        "Timed out waiting for Virtuoso to be online after "
                        f"{SERVER_STARTUP_TIMEOUT_S} seconds."
                    )
                    stop_server()
                    return False
                if log_proc is None and log_file.exists():
                    log_proc = util.run_command(
                        f"exec tail -n +1 -f {log_file}",
                        use_popen=True,
                        show_output=True,
                    )
                time.sleep(1)

            # Record this run's settings now that the server is online, so
            # that the marker lands between its "Server online" line and
            # the "Checkpoint finished" that ends the run.
            parameters = virtuoso_ini_config_dict["Parameters"]
            write_settings_marker(
                log_file,
                num_buffers=parameters["NumberOfBuffers"][0],
                max_dirty_buffers=parameters["MaxDirtyBuffers"][0],
                loaders=args.num_parallel_loaders,
                memory_for_buffers=args.memory_for_buffers,
            )

            # Execute the ld_dir and rdf_loader_run commands
            log.info("Virtuoso server online! Loading data into Virtuoso...\n")

            # Resolve virtuoso-t's PID so the resource monitor can follow
            # the detached server process in native mode.
            virtuoso_pid = None
            if args.system not in Containerize.supported_systems():
                virtuoso_pid = find_virtuoso_pid(Path("virtuoso.lck"))
                if virtuoso_pid is None:
                    log.warning(
                        "Could not resolve virtuoso-t PID from "
                        "virtuoso.lck; resource monitoring will be skipped"
                    )

            monitored = (
                args.system in Containerize.supported_systems()
                or virtuoso_pid is not None
            )
            monitor_ctx = (
                ResourceMonitor(
                    dataset=args.name,
                    binary=args.server_binary,
                    container=args.index_container,
                    system=args.system,
                    interval=args.resource_usage_interval,
                    parent_pid=virtuoso_pid,
                    # Extending keeps the runs of the existing index in the
                    # log, so that the plot covers all of them.
                    append=args.extend_existing_index,
                )
                if monitored
                else nullcontext()
            )

            with monitor_ctx:
                util.run_command(ld_dir_cmd)
                util.run_command(run_cmd)
            if log_proc is not None:
                log_proc.terminate()
            log.info("")
            log.info("Data loading has finished!")

            stop_server()

            if monitored:
                plot_path = UsagePlot(args).render()
                if plot_path is not None:
                    log.info(
                        f"Resource-usage plot saved to `{plot_path.name}`"
                    )
            else:
                log.warning(
                    "Not rendering a resource-usage plot: this run was not "
                    "monitored, so the plot would not cover it"
                )
            return True
        except Exception as e:
            log.error(f"Building the index failed: {e}")
            stop_server()
            return False
        finally:
            if log_proc is not None:
                log_proc.terminate()
