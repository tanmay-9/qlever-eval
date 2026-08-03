from __future__ import annotations

from blazegraph.commands.status import StatusCommand
from oxigraph.commands.stop import StopCommand as OxigraphStopCommand


class StopCommand(OxigraphStopCommand):
    """
    Stop a running Blazegraph server. Matches the java server process by
    the dataset's web.xml on its command line so that only the server for
    the given dataset is stopped.
    """

    STATUS_COMMAND = StatusCommand()
    # %%NAME%% is replaced with args.name at execution time
    DEFAULT_REGEX = r"java\s+-server.*%%NAME%%\.web\.xml.*blazegraph\.jar"

    def description(self) -> str:
        return "Stop Blazegraph server for a given dataset"
