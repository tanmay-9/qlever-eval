from __future__ import annotations

from configparser import RawConfigParser
from pathlib import Path

from termcolor import colored

from oxigraph.commands.setup_config import (
    SetupConfigCommand as OxigraphSetupConfigCommand,
)
from qlever.log import log
from qlever.util import add_memory_options, run_command


class SetupConfigCommand(OxigraphSetupConfigCommand):
    """
    Generate a Qleverfile and download the default virtuoso.ini configuration
    file. Extends the base setup-config with Virtuoso-specific memory budget
    options (--total-index-memory, --total-server-memory) that are used to
    auto-generate sensible Qleverfile defaults.
    """

    IMAGE = "docker.io/openlink/virtuoso-opensource-7:latest"
    VIRTUOSO_INI_URL = (
        "https://raw.githubusercontent.com/openlink/virtuoso-opensource/refs"
        "/heads/develop/7/binsrc/virtuoso/virtuoso.ini"
    )

    def additional_arguments(self, subparser) -> None:
        super().additional_arguments(subparser)
        add_memory_options(subparser)

    @staticmethod
    def construct_engine_specific_params(args) -> dict[str, dict[str, str]]:
        """
        Derive Virtuoso-specific Qleverfile parameters from the memory budget.
        Allocates 1/5 of server memory (min 2G) to the query processor.
        """
        index_params = {
            "ISQL_PORT": "1111",
            "MEMORY_FOR_BUFFERS": args.total_index_memory,
            "NUM_PARALLEL_LOADERS": "1",
        }
        total_server_memory = int(args.total_server_memory[:-1])
        max_query_memory = max(2, total_server_memory // 5)
        server_params = {
            "MAX_QUERY_MEMORY": f"{max_query_memory}G",
            "TIMEOUT": "30s",
        }
        return {"index": index_params, "server": server_params}

    def execute(self, args) -> bool:
        """
        Create the Qleverfile via the parent class, then download the default
        virtuoso.ini into the current working directory, under the name that
        `index` and `start` expect.
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
        ini_path = Path(f"{template.get('data', 'NAME')}.virtuoso.ini")

        curl_cmd = f"curl -fL --retry 3 -o {ini_path} {self.VIRTUOSO_INI_URL}"
        log.info("")
        if args.show:
            log.info(
                f"{ini_path} would be fetched using the following command:"
            )
            log.info(colored(curl_cmd, "blue"))
            return True
        ini_existed = ini_path.exists()
        try:
            log.info(f"Fetching {ini_path} configuration file...")
            run_command(cmd=curl_cmd, show_output=True, show_stderr=True)
            log.info(
                f"Successfully downloaded {ini_path} to the current working "
                "directory!"
            )
        except Exception as e:
            # A failed `curl -o` can leave an empty or partial file behind,
            # which would later pass for a config file.
            if not ini_existed:
                ini_path.unlink(missing_ok=True)
            log.error(
                f"Couldn't download the {ini_path} configuration file. "
                "If possible, please download it manually from "
                f"{self.VIRTUOSO_INI_URL} and save it as {ini_path} in the "
                f"current directory. Error -> {e}"
            )
        return True
