from __future__ import annotations

from qlever.util import parse_timeout


def qleverfile_args(all_args: dict[str, dict[str, tuple]]) -> None:
    """Define additional blazegraph specific Qleverfile parameters"""

    def arg(*args, **kwargs):
        return (args, kwargs)

    def jar_arg():
        """The same jar is needed for indexing and for serving."""
        return arg(
            "--blazegraph-jar",
            type=str,
            default="blazegraph.jar",
            help=(
                "Path to the blazegraph.jar file (default: blazegraph.jar) "
                "(this requires that you have blazegraph.jar downloaded on "
                "your machine)"
            ),
        )

    index_args = all_args["index"]
    server_args = all_args["server"]

    index_args["index_binary"] = arg(
        "--index-binary",
        type=str,
        default="java",
        help=(
            "The binary for building the index (default: java) "
            "(this requires that you have Java installed on your machine)"
        ),
    )
    index_args["blazegraph_jar"] = jar_arg()
    index_args["jvm_args"] = arg(
        "--jvm-args",
        type=str,
        default="-Xmx4G",
        help=(
            "Arguments for the JVM, for example -Xmx8G. Do not set to all "
            "available RAM. Increasing is only necessary for large numbers "
            "of long literals."
        ),
    )
    index_args["extra_args"] = arg(
        "--extra-args",
        type=str,
        default="",
        help=(
            "Additional arguments to pass directly to the Blazegraph "
            "DataLoader. This allows advanced users to specify options not "
            "exposed in Qleverfile. The string is appended verbatim to the "
            "command."
        ),
    )

    server_args["server_binary"] = arg(
        "--server-binary",
        type=str,
        default="java",
        help=(
            "The binary for starting the server (default: java) "
            "(this requires that you have Java installed on your machine)"
        ),
    )
    server_args["blazegraph_jar"] = jar_arg()
    server_args["jvm_args"] = arg(
        "--jvm-args",
        type=str,
        default="-Xmx4G",
        help=(
            "Arguments for the JVM, for example -Xmx8G. Do not set to all "
            "available RAM."
        ),
    )
    server_args["read_only"] = arg(
        "--read-only",
        type=str,
        choices=["yes", "no"],
        default="yes",
        help=(
            "The REST API will not permit mutation operations in "
            "read-only mode"
        ),
    )
    server_args["timeout"] = arg(
        "--timeout",
        type=parse_timeout,
        default="60s",
        help=(
            "The maximal time (in s) a query is allowed to run, for "
            "example 60s"
        ),
    )
    server_args["extra_args"] = arg(
        "--extra-args",
        type=str,
        default="",
        help=(
            "Additional -D props to pass directly to "
            "java -jar blazegraph.jar. This allows advanced users to "
            "specify options not exposed in Qleverfile. The string is "
            "appended verbatim to the command."
        ),
    )
