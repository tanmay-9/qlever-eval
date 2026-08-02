from __future__ import annotations

from oxigraph.commands.status import StatusCommand as OxigraphStatusCommand


class StatusCommand(OxigraphStatusCommand):
    """Show running virtuoso-t processes by matching the process name."""

    DEFAULT_REGEX = "virtuoso-t"

    def description(self) -> str:
        return "Show Virtuoso processes running on this machine"
