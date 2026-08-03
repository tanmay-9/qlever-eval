from __future__ import annotations

from oxigraph.commands.status import StatusCommand as OxigraphStatusCommand


class StatusCommand(OxigraphStatusCommand):
    """
    Show running Blazegraph server processes by matching the java command
    line that runs blazegraph.jar.
    """

    DEFAULT_REGEX = r"java\s+-server.*blazegraph\.jar"

    def description(self) -> str:
        return (
            "Show Java processes with blazegraph.jar running on this machine"
        )
