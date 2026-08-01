from __future__ import annotations

from pathlib import Path

import qlever.util as util
from qlever import script_name
from qlever.log import log


def virtuoso_ini_missing_msg(args) -> str:
    """Message for a missing <name>.virtuoso.ini."""
    return (
        f"{args.name}.virtuoso.ini config file not found in the current "
        f"directory! Did you call `{script_name} {args.engine} setup-config`?"
    )


def virtuoso_ini_exists(args) -> bool:
    """
    Whether index and start will find an ini to update, either under its
    proper name or as a virtuoso.ini that `resolve_virtuoso_ini` renames.
    """
    return (
        Path(f"{args.name}.virtuoso.ini").exists()
        or Path("virtuoso.ini").exists()
    )


def resolve_virtuoso_ini(args) -> bool:
    """
    Make sure <name>.virtuoso.ini exists, renaming a virtuoso.ini left by
    an older setup-config or downloaded by hand to it. False if there is
    no such file.
    """
    ini_path = Path(f"{args.name}.virtuoso.ini")
    if ini_path.exists():
        return True
    default_ini = Path("virtuoso.ini")
    if not default_ini.exists():
        log.error(virtuoso_ini_missing_msg(args))
        return False
    default_ini.rename(ini_path)
    log.info(f"{default_ini} renamed to {ini_path}!")
    return True


def update_virtuoso_ini(
    name: str,
    config_dict: dict[str, dict[str, tuple[str, bool]]],
) -> bool:
    """
    Read the virtuoso.ini file, apply the updates from config_dict,
    and write it back.
    """
    ini_path = Path(f"{name}.virtuoso.ini")
    try:
        lines = ini_path.read_text().splitlines()
        result = util.update_ini_values(lines, config_dict)
        ini_path.write_text("\n".join(result) + "\n")
        return True
    except Exception as e:
        log.error(f"Couldn't update {ini_path}: {e}")
        return False


def log_virtuoso_ini_changes(
    name: str,
    config_dict: dict[str, dict[str, tuple[str, bool]]],
):
    """
    Log the section/option values that will be written to virtuoso.ini.
    Called before execution so the user can review what will change.
    """
    log.info(
        f"Following options of {name}.virtuoso.ini will be updated "
        "with the values from Qleverfile:\n"
    )
    for section, option_dict in config_dict.items():
        log_values = [f"[{section}]"]
        for option, (new_value, _) in option_dict.items():
            log_values.append(f"{option}  =  {new_value}")
        log.info("\n".join(log_values))
        log.info("")
