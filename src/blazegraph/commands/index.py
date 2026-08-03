from __future__ import annotations

from pathlib import Path

from blazegraph import BLAZEGRAPH_JAR_URL
from blazegraph.resource_usage.usage_plot import UsagePlot
from qlever.command import QleverCommand
from qlever.containerize import Containerize
from qlever.log import log
from qlever.resource_usage.resource_monitor import ResourceMonitor
from qlever.util import (
    binary_exists,
    build_image,
    get_container_image_id,
    input_files_exist,
    run_command,
)


def wrap_cmd_in_container(args, cmd: str) -> str:
    """
    Wrap an indexing command in a container that is automatically
    removed after the process exits (--rm).
    """
    return Containerize().containerize_command(
        cmd=cmd,
        container_system=args.system,
        run_subcommand="run --rm",
        image_name=args.image,
        container_name=args.index_container,
        volumes=[("$(pwd)", "/opt/index")],
        working_directory="/opt/index",
    )


class IndexCommand(QleverCommand):
    """
    Build a Blazegraph journal for an RDF dataset by running the DataLoader
    against RWStore.properties. Supports native and containerized
    execution; the image is built from the Dockerfile shipped with this
    package.
    """

    def __init__(self):
        pass

    def description(self) -> str:
        return "Build the index for a given RDF dataset"

    def should_have_qleverfile(self) -> bool:
        return True

    def relevant_qleverfile_arguments(self) -> dict[str, list[str]]:
        return {
            "data": ["name", "format"],
            "index": [
                "input_files",
                "index_binary",
                "blazegraph_jar",
                "jvm_args",
                "extra_args",
                "resource_usage_interval",
                "resource_usage_plot_max_points",
            ],
            "runtime": ["system", "image", "index_container"],
        }

    def additional_arguments(self, subparser):
        subparser.add_argument(
            "--rebuild-image",
            action="store_true",
            default=False,
            help="Rebuild the Docker image to get the latest updates",
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

        system = args.system
        input_files = args.input_files
        containerized = system in Containerize.supported_systems()

        # In a container the jar is the one baked into the image by the
        # Dockerfile, which downloads it to its /opt working directory.
        jar_path = (
            "/opt/blazegraph.jar" if containerized else args.blazegraph_jar
        )

        index_cmd = (
            f"{args.index_binary} {args.jvm_args} -cp {jar_path} "
            f"com.bigdata.rdf.store.DataLoader"
        )
        if args.extra_args:
            index_cmd += f" {args.extra_args}"
        index_cmd += f" RWStore.properties {input_files}"
        # DataLoader logs through log4j, which writes to stderr, so both
        # streams have to be captured for the log to be complete.
        index_cmd += f" 2>&1 | tee {args.name}.index-log.txt"

        image_id = build_cmd = ""
        if containerized:
            index_cmd = wrap_cmd_in_container(args, index_cmd)
            dockerfile_dir = Path(__file__).parent.parent
            dockerfile_path = dockerfile_dir / "Dockerfile"
            build_cmd = (
                f"{system} build -f {dockerfile_path} -t {args.image} "
                f"--build-arg UID=$(id -u) --build-arg GID=$(id -g) "
                f"{dockerfile_dir}"
            )
            image_id = get_container_image_id(system, args.image)
            cmd_to_show = (
                f"{build_cmd}\n\n{index_cmd}"
                if not image_id or args.rebuild_image
                else index_cmd
            )
        else:
            cmd_to_show = index_cmd

        # Show the command line.
        self.show(cmd_to_show, only_show=args.show)
        if args.show:
            return True

        # Check if all of the input files exist.
        if not input_files_exist(input_files, args.engine):
            return False

        if containerized:
            if Containerize().is_running(args.system, args.index_container):
                log.info(
                    f"{args.system} container {args.index_container} is "
                    "still up, which means that data loading is in "
                    "progress. Please wait..."
                )
                return False
        else:
            # When running natively, check if the binary exists and works.
            if not binary_exists(args.index_binary, "index-binary", args):
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

        index_jnl = Path("blazegraph.jnl")
        if index_jnl.exists():
            log.error(
                "Blazegraph journal blazegraph.jnl found in current working "
                "directory which shows presence of a previous index\n"
            )
            log.info("Aborting the index operation...")
            return False

        # Build the container image if not found on the system.
        if containerized:
            if not image_id or args.rebuild_image:
                if not build_image(build_cmd, system, args.image):
                    return False
            else:
                log.info(f"{args.image} image present on the system\n")

        # Run the index command.
        try:
            with ResourceMonitor.from_args(args):
                run_command(index_cmd, show_output=True)
        except Exception as e:
            log.error(f"Building the index failed: {e}")
            return False

        plot_path = UsagePlot(args).render()
        if plot_path is not None:
            log.info(f"Resource-usage plot saved to `{plot_path.name}`")

        return True
