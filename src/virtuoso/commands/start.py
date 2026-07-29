from __future__ import annotations

import shutil
import time
from pathlib import Path

from qlever import script_name
from qlever.command import QleverCommand
from qlever.containerize import Containerize
from qlever.log import log
from qlever.util import is_server_alive, run_command, tail_log_file
from virtuoso.commands.index import (
    log_virtuoso_ini_changes,
    resolve_virtuoso_ini,
    update_virtuoso_ini,
    virtuoso_ini_missing_msg,
)
from virtuoso.commands.stop import StopCommand

VIRTUOSO_MAX_RESULT_ROWS = 1048576


def server_ini_config(args) -> dict[str, dict[str, tuple[str, bool]]]:
    """
    The virtuoso.ini sections and options that `start` needs to update.
    Each value is a (new_value, is_suffix) tuple.
    """
    http_port = (
        str(args.port)
        if args.system in Containerize.supported_systems()
        else f"{args.host_name}:{args.port}"
    )

    # `parse_timeout` guarantees the `<int>s` shape, so this cannot raise.
    timeout_s = int(args.timeout[:-1])

    return {
        "Parameters": {
            "MaxQueryMem": (str(args.max_query_memory), False),
        },
        "HTTPServer": {
            "ServerPort": (http_port, False),
        },
        "Database": {
            "ErrorLogFile": (f"{args.name}.server-log.txt", False),
        },
        "SPARQL": {
            "MaxQueryCostEstimationTime": ("-1", False),
            "ResultSetMaxRows": (str(VIRTUOSO_MAX_RESULT_ROWS), False),
            "MaxQueryExecutionTime": (str(timeout_s), False),
        },
    }


def wrap_cmd_in_container(args, cmd: str) -> str:
    """
    Wrap the server start command in a container with restart policy.

    No `working_directory` is needed: the Virtuoso image already has
    /database as its working directory, which is where the current
    directory is mounted, so relative paths resolve into the mount.
    """
    run_subcommand = "run --restart=unless-stopped --group-add virtuoso"
    if not args.run_in_foreground:
        run_subcommand += " -d"
    return Containerize().containerize_command(
        cmd=cmd,
        container_system=args.system,
        run_subcommand=run_subcommand,
        image_name=args.image,
        container_name=args.server_container,
        volumes=[("$(pwd)", "/database")],
        ports=[(args.port, args.port)],
    )


class StartCommand(QleverCommand):
    """
    Start the Virtuoso server (virtuoso-t) for an already-indexed dataset.
    Before starting, updates virtuoso.ini with Qleverfile settings (ports,
    timeouts, query memory, SPARQL limits). Supports both native and
    containerized execution, with an option to run in the foreground.
    """

    def __init__(self):
        pass

    def description(self) -> str:
        return (
            "Start the server for Virtuoso (requires that you have built an "
            "index before)"
        )

    def should_have_qleverfile(self) -> bool:
        return True

    def relevant_qleverfile_arguments(self) -> dict[str, list[str]]:
        return {
            "data": ["name"],
            "server": [
                "host_name",
                "port",
                "server_binary",
                "timeout",
                "max_query_memory",
                "extra_args",
            ],
            "runtime": ["system", "image", "server_container"],
        }

    def additional_arguments(self, subparser):
        subparser.add_argument(
            "--run-in-foreground",
            action="store_true",
            default=False,
            help=(
                "Run the start command in the foreground "
                "(default: run in the background)"
            ),
        )

    def execute(self, args) -> bool:
        start_cmd = (
            f"{args.server_binary} -c {args.name}.virtuoso.ini "
            f"{args.extra_args}"
        ).rstrip()
        if args.system in Containerize.supported_systems():
            start_cmd = wrap_cmd_in_container(args, f"{start_cmd} -f")
        elif args.run_in_foreground:
            start_cmd += " -f"

        if args.show and not Path(f"{args.name}.virtuoso.ini").exists():
            ini_files = [str(ini) for ini in Path(".").glob("*.ini")]
            self.show(virtuoso_ini_missing_msg(args, ini_files))

        virtuoso_ini_config_dict = server_ini_config(args)
        log_virtuoso_ini_changes(args.name, virtuoso_ini_config_dict)
        # Show the command line.
        self.show(start_cmd, only_show=args.show)
        if args.show:
            return True

        endpoint_url = f"http://{args.host_name}:{args.port}/sparql"

        # When running natively, check if the binary exists and works.
        # We use shutil.which instead of util.binary_exists because
        # virtuoso-t --help writes to stderr instead of stdout
        if args.system not in Containerize.supported_systems():
            if not shutil.which(args.server_binary):
                log.error(
                    f'Running "{args.server_binary}" failed, '
                    "set `--server-binary` to a different binary or "
                    "set `--system to a container system`"
                )
                return False

        # Check if index db virtuoso.db present in cwd
        if not Path("virtuoso.db").exists():
            log.error(f"No Virtuoso index db for {args.name} found!\n")
            log.info(
                f"Did you call `{script_name} {args.engine} index`? If you "
                "did, check if virtuoso.db is present in current working "
                "directory."
            )
            return False

        if is_server_alive(url=endpoint_url):
            log.error(f"Virtuoso server already running on {endpoint_url}\n")
            log.info(
                "To kill the existing server, use "
                f"`{script_name} {args.engine} stop`"
            )
            return False

        if not resolve_virtuoso_ini(args):
            return False

        if not update_virtuoso_ini(args.name, virtuoso_ini_config_dict):
            return False

        # Remove old log file so that tail starts clean.
        log_file = Path(f"{args.name}.server-log.txt")
        log_file.unlink(missing_ok=True)

        try:
            process = run_command(
                start_cmd,
                use_popen=args.run_in_foreground,
            )
        except Exception as e:
            log.error(f"Starting the Virtuoso server failed ({e})")
            return False

        # Tail the server log until the server is ready (note that the `exec`
        # is important to make sure that the tail process is killed and not
        # just the bash process).
        if args.run_in_foreground:
            log.info(
                "Follow the server logs as long as the server is"
                " running (Ctrl-C stops the server)"
            )
        else:
            log.info(
                "Follow the server logs until the server is ready"
                " (Ctrl-C stops following the log, but NOT the server)"
            )
        log.info("")
        log_proc = tail_log_file(log_file)
        if log_proc is None:
            return False
        while not is_server_alive(endpoint_url):
            time.sleep(1)

        log.info(
            f"Virtuoso server webapp for {args.name} will be available "
            f"at http://{args.host_name}:{args.port} and the sparql "
            f"endpoint for queries is http://{args.host_name}:{args.port}/sparql"
        )

        # Kill the log process
        if not args.run_in_foreground:
            log_proc.terminate()

        # With `--run-in-foreground`, wait until the server is stopped.
        if args.run_in_foreground:
            try:
                process.wait()
            except KeyboardInterrupt:
                process.terminate()
                # Remove the container if the user stops the server process
                if args.system in Containerize.supported_systems():
                    args.cmdline_regex = StopCommand.DEFAULT_REGEX
                    StopCommand().execute(args)
            log_proc.terminate()

        return True
