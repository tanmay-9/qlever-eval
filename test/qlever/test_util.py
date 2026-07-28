import argparse
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from qlever.util import (
    container_memory_to_bytes,
    follow_server_log,
    get_random_string,
    parse_git_hash,
    positive_int,
    server_liveness_check,
    wait_for_foreground_server,
    wait_until_server_ready,
)

MODULE = "qlever.util"


def test_get_random_string():
    random_string_1 = get_random_string(20)
    random_string_2 = get_random_string(20)
    assert len(random_string_1) == 20
    assert len(random_string_2) == 20
    assert random_string_1 != random_string_2


@pytest.mark.parametrize(
    "usage,expected",
    [
        ("2TiB", 2 * 1024**4),
        ("1.5GiB", int(1.5 * 1024**3)),
        ("512MiB", 512 * 1024**2),
        ("4KiB", 4 * 1024),
        ("2TB", 2 * 1000**4),
        ("1.5GB", int(1.5 * 1000**3)),
        ("512MB", 512 * 1000**2),
        ("4KB", 4 * 1000),
        ("100B", 100),
        ("0B", 0),
        # Longest matching suffix wins; "GiB"/"GB" must not be read as
        # bare bytes via the trailing "B".
        ("2GiB", 2 * 1024**3),
        ("2GB", 2 * 1000**3),
        # Leading/trailing whitespace and case are tolerated.
        ("  1.5gib ", int(1.5 * 1024**3)),
        # A space between number and unit is accepted by float().
        ("1.5 GiB", int(1.5 * 1024**3)),
        ("", 0),
        ("garbage", 0),
    ],
)
def test_container_memory_to_bytes(usage, expected):
    assert container_memory_to_bytes(usage) == expected


@pytest.mark.parametrize(
    "first_line,expected",
    [
        ("qlever-server, git hash 1a2b3c4, compiled", "1a2b3c4"),
        ("no hash on this line", None),
    ],
)
def test_parse_git_hash_reads_first_line_only(first_line, expected, tmp_path):
    path = tmp_path / "index-log.txt"
    # Second line also carries a hash; only the first line should count.
    path.write_text(first_line + "\nsomething git hash deadbeef here\n")
    assert parse_git_hash(path) == expected


@pytest.mark.parametrize("value,expected", [("1", 1), ("500", 500)])
def test_positive_int_accepts(value, expected):
    assert positive_int(value) == expected


@pytest.mark.parametrize("value", ["0", "-3"])
def test_positive_int_rejects_non_positive(value):
    with pytest.raises(argparse.ArgumentTypeError):
        positive_int(value)


@pytest.mark.parametrize("value", ["1.5", "abc"])
def test_positive_int_rejects_non_integer(value):
    # argparse also treats a plain `ValueError` as invalid input
    with pytest.raises(ValueError):
        positive_int(value)


def test_parse_git_hash_missing_file(tmp_path):
    assert parse_git_hash(tmp_path / "nope.txt") is None


def test_parse_git_hash_empty_file(tmp_path):
    path = tmp_path / "empty.txt"
    path.write_text("")
    assert parse_git_hash(path) is None


def alive_after(num_polls: int):
    """A readiness check that says yes on the `num_polls`-th call."""
    polls = 0

    def is_alive() -> bool:
        nonlocal polls
        polls += 1
        return polls > num_polls

    return is_alive


def never_alive(max_polls: int = 10):
    """
    A readiness check that never says yes. It fails the test after
    `max_polls` calls, so that a wait loop which does not stop makes the
    test fail instead of hang.
    """
    polls = 0

    def is_alive() -> bool:
        nonlocal polls
        polls += 1
        assert polls <= max_polls, "waited for a server that never comes up"
        return False

    return is_alive


def test_wait_until_server_ready_when_alive_right_away():
    never_called = MagicMock(side_effect=AssertionError("checked liveness"))
    assert wait_until_server_ready(lambda: True, never_called) is True


def test_wait_until_server_ready_polls_until_alive():
    is_still_running = MagicMock(return_value=True)
    ready = wait_until_server_ready(
        alive_after(3), is_still_running, poll_interval_s=0
    )
    assert ready is True
    assert is_still_running.call_count == 3


def test_wait_until_server_ready_gives_up_when_process_died(mock_command):
    log_mock = mock_command(MODULE, "log")
    ready = wait_until_server_ready(
        never_alive(), lambda: False, poll_interval_s=0
    )
    assert ready is False
    log_mock.error.assert_called_once_with(
        "Server process exited before becoming ready"
    )


def test_wait_until_server_ready_polls_until_process_dies():
    # The server is never ready and dies on the third check.
    is_still_running = MagicMock(side_effect=[True, True, False])
    ready = wait_until_server_ready(
        never_alive(), is_still_running, poll_interval_s=0
    )
    assert ready is False
    assert is_still_running.call_count == 3


@pytest.mark.parametrize("system", ["docker", "podman"])
def test_server_liveness_check_uses_container_state(system, monkeypatch):
    is_running = MagicMock(return_value=False)
    monkeypatch.setattr(
        "qlever.containerize.Containerize.is_running", is_running
    )
    args = argparse.Namespace(
        system=system,
        server_container="qlever.server.test",
        run_in_foreground=False,
    )
    assert server_liveness_check(args, None)() is False
    is_running.assert_called_once_with(system, "qlever.server.test")


@pytest.mark.parametrize(
    "poll_result,expected", [(None, True), (0, False), (1, False)]
)
def test_server_liveness_check_polls_foreground_process(poll_result, expected):
    process = MagicMock()
    process.poll.return_value = poll_result
    args = argparse.Namespace(
        system="native", server_container=None, run_in_foreground=True
    )
    assert server_liveness_check(args, process)() is expected


def test_server_liveness_check_assumes_alive_with_nohup():
    # Started with `nohup`, so there is no handle on the server process
    # even though the one we have has exited.
    process = MagicMock()
    process.poll.return_value = 1
    args = argparse.Namespace(
        system="native", server_container=None, run_in_foreground=False
    )
    assert server_liveness_check(args, process)() is True


def test_follow_server_log_attaches_to_the_log_file():
    attach = MagicMock(return_value="log process")
    log_file = Path("test.server-log.txt")
    assert follow_server_log(log_file, False, attach) == "log process"
    attach.assert_called_once_with(log_file)


def test_follow_server_log_returns_none_when_attaching_fails():
    assert follow_server_log(Path("x.txt"), False, lambda _: None) is None


@pytest.mark.parametrize(
    "run_in_foreground,expected",
    [
        (True, "as long as the server is running"),
        (False, "until the server is ready"),
    ],
)
def test_follow_server_log_message(run_in_foreground, expected, mock_command):
    log_mock = mock_command(MODULE, "log")
    follow_server_log(
        Path("test.server-log.txt"), run_in_foreground, lambda _: None
    )
    message = log_mock.info.call_args_list[0].args[0]
    assert message.startswith("Follow test.server-log.txt ")
    assert expected in message


def test_follow_server_log_message_with_log_name(mock_command):
    log_mock = mock_command(MODULE, "log")
    follow_server_log(
        Path("test.server-log.txt"),
        False,
        lambda _: None,
        log_name="the logs of container test",
    )
    message = log_mock.info.call_args_list[0].args[0]
    assert message.startswith("Follow the logs of container test ")
    assert "test.server-log.txt" not in message


def test_wait_for_foreground_server_until_it_stops():
    process, log_proc, on_interrupt = MagicMock(), MagicMock(), MagicMock()
    wait_for_foreground_server(process, log_proc, on_interrupt)
    process.wait.assert_called_once()
    process.terminate.assert_not_called()
    on_interrupt.assert_not_called()
    log_proc.terminate.assert_called_once()


def test_wait_for_foreground_server_stops_it_on_ctrl_c(mock_command):
    log_mock = mock_command(MODULE, "log")
    process, log_proc, on_interrupt = MagicMock(), MagicMock(), MagicMock()
    process.wait.side_effect = KeyboardInterrupt
    wait_for_foreground_server(process, log_proc, on_interrupt)
    log_mock.warning.assert_called_once()
    process.terminate.assert_called_once()
    on_interrupt.assert_called_once()
    log_proc.terminate.assert_called_once()
