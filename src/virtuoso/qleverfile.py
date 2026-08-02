from __future__ import annotations

from qlever.util import parse_memory, parse_timeout


def qleverfile_args(all_args: dict[str, dict[str, tuple]]) -> None:
    """
    Define Virtuoso-specific Qleverfile parameters for the [index] and
    [server] sections. These include the isql binary/port for indexing,
    parallel loader count, memory allocation, and the virtuoso-t server
    binary with its query memory and timeout settings.
    """

    def arg(*args, **kwargs):
        return (args, kwargs)

    index_args = all_args["index"]
    server_args = all_args["server"]

    index_args["index_binary"] = arg(
        "--index-binary",
        type=str,
        default="isql",
        help=(
            "The isql binary for building the index (default: isql) "
            "(this requires that you have virtuoso binaries installed "
            "on your machine)"
        ),
    )
    index_args["isql_port"] = arg(
        "--isql-port",
        type=int,
        default=1111,
        help="The port used by Virtuoso's ISQL index binary",
    )
    index_args["num_parallel_loaders"] = arg(
        "--num-parallel-loaders",
        type=int,
        default=1,
        choices=range(1, 11),
        help=(
            "Number of rdf_loader_run() processes loading the input files "
            "in parallel (default: 1). At most cores / 2.5 is recommended."
        ),
    )
    index_args["memory_for_buffers"] = arg(
        "--memory-for-buffers",
        type=parse_memory,
        default="4G",
        help=(
            "Memory for Virtuoso's buffer pool, for example 8G. "
            "NumberOfBuffers and MaxDirtyBuffers are derived from it. "
            "Virtuoso recommends about 2/3 of system memory."
        ),
    )

    server_args["server_binary"] = arg(
        "--server-binary",
        type=str,
        default="virtuoso-t",
        help=(
            "The binary for starting the server (default: virtuoso-t) "
            "(this requires that you have virtuoso binaries installed "
            "on your machine)"
        ),
    )
    server_args["max_query_memory"] = arg(
        "--max-query-memory",
        type=str,
        default="2G",
        help="The memory allocated to query processor.",
    )
    server_args["timeout"] = arg(
        "--timeout",
        type=parse_timeout,
        default="30s",
        help=(
            "The maximal time in seconds a query is allowed to run, for "
            "example 30s"
        ),
    )
    server_args["extra_args"] = arg(
        "--extra-args",
        type=str,
        default="",
        help=(
            "Additional arguments to pass directly to the virtuoso-t binary. "
            "This allows advanced users to specify options not exposed in "
            "Qleverfile. The string is appended verbatim to the command."
        ),
    )
