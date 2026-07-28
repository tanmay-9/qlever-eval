from __future__ import annotations

from oxigraph.commands.query import QueryCommand as OxigraphQueryCommand


class QueryCommand(OxigraphQueryCommand):
    """
    Send a SPARQL query to the MillenniumDB server. Extends the base query
    command with MillenniumDB's /sparql endpoint.
    """

    def execute(self, args) -> bool:
        if not args.sparql_endpoint:
            args.sparql_endpoint = f"{args.host_name}:{args.port}/sparql"
        return super().execute(args)
