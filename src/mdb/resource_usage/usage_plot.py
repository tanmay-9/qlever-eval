from __future__ import annotations

from qlever.containerize import Containerize
from qlever.resource_usage.usage_plot import UsagePlot as BaseUsagePlot
from qlever.util import run_command


class UsagePlot(BaseUsagePlot):
    """Resource-usage plot for a MillenniumDB index build."""

    def overlay(self) -> list[tuple[str, float, float]]:
        """No phase shading: mdb's index log has no timestamped phase
        markers for the base parser to locate."""
        return []

    def subtitle(self) -> str | None:
        """Assemble a 'version | btree' line from the index args."""
        if self.args.system in Containerize.supported_systems():
            version_cmd = (
                f"{self.args.system} run --rm {self.args.image} --version"
            )
        else:
            version_cmd = f"{self.args.index_binary} --version"
        try:
            version = run_command(version_cmd, return_output=True).strip()
        except Exception:
            version = ""
        parts = []
        if version:
            parts.append(version)
        parts.append(f"buffer-strings = {self.args.buffer_strings}")
        parts.append(f"buffer-tensors = {self.args.buffer_tensors}")
        return "   |   ".join(parts)
