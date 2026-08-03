from __future__ import annotations

from configparser import RawConfigParser
from importlib.resources import files
from pathlib import Path

from oxigraph.commands.setup_config import (
    SetupConfigCommand as OxigraphSetupConfigCommand,
)
from qlever.log import log
from qlever.util import add_memory_options


class SetupConfigCommand(OxigraphSetupConfigCommand):
    """
    Create a Qleverfile for Blazegraph from a dataset template, alongside
    the two files Blazegraph needs to run: RWStore.properties (journal and
    loader settings) and <name>.web.xml (query timeout and read-only
    mode). Both are shipped with the package and match the pinned
    blazegraph.jar.
    """

    IMAGE = "adfreiburg/blazegraph"

    @staticmethod
    def construct_engine_specific_params(args) -> dict[str, dict[str, str]]:
        index_memory = args.total_index_memory
        server_memory = args.total_server_memory
        return {
            "index": {"JVM_ARGS": f"-Xms{index_memory} -Xmx{index_memory}"},
            "server": {
                "JVM_ARGS": f"-Xms{server_memory} -Xmx{server_memory}",
                "TIMEOUT": "60s",
                "READ_ONLY": "yes",
            },
        }

    def additional_arguments(self, subparser) -> None:
        super().additional_arguments(subparser)
        add_memory_options(subparser)

    def execute(self, args) -> bool:
        """
        Create the Qleverfile via the parent class, then copy the two
        configuration files shipped with the package into the current
        working directory, under the names `index` and `start` expect.
        """
        qleverfile_successfully_created = super().execute(args)
        if not qleverfile_successfully_created:
            return False

        # From the template, not the Qleverfile, which does not exist yet
        # with `--show`. The two hold the same name, since `[data]` is
        # copied verbatim.
        template = RawConfigParser()
        template.optionxform = str
        template.read(self.qleverfiles_path / f"Qleverfile.{args.config_name}")
        name = template.get("data", "NAME")

        files_to_copy = {
            "RWStore.properties": Path("RWStore.properties"),
            "web.xml": Path(f"{name}.web.xml"),
        }

        log.info("")
        if args.show:
            for destination in files_to_copy.values():
                log.info(
                    f"{destination} would be copied to the current directory"
                )
            return True

        for resource, destination in files_to_copy.items():
            source = files("blazegraph").joinpath(resource)
            try:
                destination.write_text(source.read_text())
            except OSError as e:
                log.error(f"Could not create {destination}: {e}")
                log.info(
                    f"Copy it manually from {source} to {destination} "
                    "in the current directory"
                )
                return False
            log.info(f"Created {destination} in the current directory")

        return True
