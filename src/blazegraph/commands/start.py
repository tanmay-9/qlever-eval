from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from blazegraph import BLAZEGRAPH_JAR_URL
from blazegraph.commands.stop import StopCommand
from qlever import script_name
from qlever.command import QleverCommand
from qlever.containerize import Containerize
from qlever.log import log
from qlever.util import (
    binary_exists,
    follow_server_log,
    is_server_alive,
    run_command,
    server_liveness_check,
    wait_for_foreground_server,
    wait_until_server_ready,
)


def wrap_cmd_in_container(args, cmd: str) -> str:
    """Wrap the server start command in a container with restart policy."""
    run_subcommand = "run --restart=unless-stopped"
    if not args.run_in_foreground:
        run_subcommand += " -d"
    return Containerize().containerize_command(
        cmd=cmd,
        container_system=args.system,
        run_subcommand=run_subcommand,
        image_name=args.image,
        container_name=args.server_container,
        volumes=[("$(pwd)", "/opt/index")],
        working_directory="/opt/index",
        ports=[(args.port, args.port)],
    )


def overwrite_web_xml(
    xml_file_path: Path, timeout_ms: int, read_only: bool
) -> None:
    """
    Set the queryTimeout and readOnly context-params in web.xml, which is
    the only place Blazegraph takes them from.
    """
    new_values = {
        "queryTimeout": str(timeout_ms),
        "readOnly": str(read_only).lower(),
    }
    ns_uri = "http://java.sun.com/xml/ns/javaee"
    namespace = {"ns": "http://java.sun.com/xml/ns/javaee"}

    # Register the default namespace to avoid ns0 prefixes
    ET.register_namespace("", ns_uri)

    # Parse the XML and preserve comments
    parser = ET.XMLParser(target=ET.TreeBuilder(insert_comments=True))
    tree = ET.parse(xml_file_path, parser=parser)
    root = tree.getroot()

    # Find and update values
    for context_param in root.findall("ns:context-param", namespace):
        param_name = context_param.find("ns:param-name", namespace)
        if param_name is not None and param_name.text in new_values:
            param_value = context_param.find("ns:param-value", namespace)
            if param_value is not None:
                param_value.text = new_values[param_name.text]
    tree.write(xml_file_path, encoding="UTF-8", xml_declaration=True)
    log.info(f"Successfully updated {xml_file_path.name}.")


class StartCommand(QleverCommand):
    """
    Start the Blazegraph server for an already-indexed dataset. The
    timeout and read-only settings are applied by rewriting
    `<name>.web.xml`, which is the only place Blazegraph reads them from.
    """

    def __init__(self):
        pass

    def description(self) -> str:
        return (
            "Start the server for Blazegraph (requires that you have built an "
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
                "blazegraph_jar",
                "jvm_args",
                "read_only",
                "timeout",
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
        containerized = args.system in Containerize.supported_systems()
        jar_path = (
            "/opt/blazegraph.jar" if containerized else args.blazegraph_jar
        )
        web_xml = Path(f"{args.name}.web.xml")

        # `-jar` has to come last: Java passes everything after it to the
        # program, and `stop` matches the jar at the end of the command.
        start_cmd = (
            f"{args.server_binary} -server {args.jvm_args} "
            f"-Dbigdata.propertyFile=RWStore.properties "
            f"-Djetty.overrideWebXml={web_xml} "
            f"-Djetty.port={args.port}"
        )
        if args.extra_args:
            start_cmd += f" {args.extra_args}"
        start_cmd += f" -jar {jar_path} > {args.name}.server-log.txt 2>&1"

        if containerized:
            start_cmd = wrap_cmd_in_container(args, start_cmd)
        elif not args.run_in_foreground:
            start_cmd = f"nohup {start_cmd} &"

        # Show the command line.
        self.show(start_cmd, only_show=args.show)
        if args.show:
            return True

        # When running natively, check if the binary exists and works.
        if not containerized:
            if not binary_exists(args.server_binary, "server-binary", args):
                return False
            if not Path(args.blazegraph_jar).exists():
                log.error(
                    "Couldn't find the blazegraph.jar in specified path: "
                    f"{Path(args.blazegraph_jar).absolute()}\n"
                )
                log.info(
                    "Are you sure you downloaded the blazegraph.jar file? "
                    f"blazegraph.jar can be downloaded from "
                    f"{BLAZEGRAPH_JAR_URL}"
                )
                return False

        if not Path("blazegraph.jnl").exists():
            log.error(f"No Blazegraph journal for {args.name} found!\n")
            log.info(
                f"Did you call `{script_name} {args.engine} index`? If you "
                "did, check if blazegraph.jnl is present in the current "
                "working directory"
            )
            return False

        # The timeout and read-only settings are applied through web.xml,
        # so the server cannot be started without it.
        if not web_xml.exists():
            log.error(f"No {web_xml} found!\n")
            log.info(
                f"Run `{script_name} {args.engine} setup-config <dataset>` "
                "to write it again"
            )
            return False

        endpoint_url = f"http://{args.host_name}:{args.port}/blazegraph"
        if is_server_alive(url=endpoint_url):
            log.error(f"Blazegraph server already running on {endpoint_url}\n")
            log.info(
                "To kill the existing server, use "
                f"`{script_name} {args.engine} stop`"
            )
            return False

        try:
            overwrite_web_xml(
                web_xml, int(args.timeout[:-1]) * 1000, args.read_only == "yes"
            )
        except Exception as e:
            log.error(
                f"Overwriting {web_xml} with Qleverfile parameters failed: {e}"
            )
            return False

        # Remove old log file so that tail starts clean.
        log_file = Path(f"{args.name}.server-log.txt")
        log_file.unlink(missing_ok=True)

        # Run the start command.
        try:
            process = run_command(
                start_cmd,
                use_popen=args.run_in_foreground,
            )
        except Exception as e:
            log.error(f"Starting the Blazegraph server failed ({e})")
            return False

        # Tail the server log until the server is ready.
        log_proc = follow_server_log(log_file, args.run_in_foreground)
        if log_proc is None:
            return False
        if not wait_until_server_ready(
            lambda: is_server_alive(endpoint_url),
            server_liveness_check(args, process),
        ):
            log_proc.terminate()
            return False

        log.info(
            f"Blazegraph server webapp for {args.name} will be available at "
            f"http://{args.host_name}:{args.port} and the sparql endpoint for "
            f"queries is {endpoint_url}/namespace/kb/sparql"
        )

        # Kill the log process
        if not args.run_in_foreground:
            log_proc.terminate()

        # With `--run-in-foreground`, wait until the server is stopped.
        # On Ctrl-C, terminate the process and clean up the container.
        if args.run_in_foreground:

            def stop_container() -> None:
                # Remove the container if the user stops the server process
                if containerized:
                    args.cmdline_regex = StopCommand.DEFAULT_REGEX
                    StopCommand().execute(args)

            wait_for_foreground_server(process, log_proc, stop_container)

        return True
