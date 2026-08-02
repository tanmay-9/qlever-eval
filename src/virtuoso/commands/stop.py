from __future__ import annotations

from oxigraph.commands.stop import StopCommand as OxigraphStopCommand
from virtuoso.commands.status import StatusCommand


class StopCommand(OxigraphStopCommand):
    """
    Stop a running Virtuoso server. Matches the virtuoso-t process by
    its config file argument (-c <name>.virtuoso.ini) so that only the
    server for the given dataset is stopped.
    """

    STATUS_COMMAND = StatusCommand()
    # %%NAME%% is replaced with args.name at execution time
    DEFAULT_REGEX = r"virtuoso-t.*-c\s%%NAME%%.*"

    def description(self) -> str:
        return "Stop Virtuoso server for a given dataset or port"
