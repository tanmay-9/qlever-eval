from __future__ import annotations

from oxigraph.commands.query import QueryCommand as OxigraphQueryCommand


class QueryCommand(OxigraphQueryCommand):
    """
    Send a SPARQL query to the Blazegraph server. Extends the base query
    command with Blazegraph's endpoint for the `kb` namespace.
    """

    def execute(self, args) -> bool:
        if not args.sparql_endpoint:
            args.sparql_endpoint = (
                f"{args.host_name}:{args.port}/blazegraph/namespace/kb/sparql"
            )
        return super().execute(args)
