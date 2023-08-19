import pathlib
import threading
import ipaddress
import logging
import socket
import time
import subprocess
from rich.table import Column
from rich.progress import Progress, BarColumn, TextColumn
from rich.progress import Progress


REPO_NAME = "RACR_AI"


logger = logging.getLogger("tracr_logger")


def get_tracr_root() -> pathlib.Path:
    """
    Returns the root directory of the TRACR project as a pathlib.Path object.
    Does not matter where this function is called from, as long as it is
    called from within the TRACR project directory (which should be the case)
    """
    result = pathlib.Path(__file__).parent.absolute()
    logger.debug(f"get_tracr_root() starting search from {result}")
    parts = str(result).split("/")
    parts = parts[1:]
    parts[0] = "/" + parts[0]
    logger.debug(f"get_tracr_root() parts: {parts}")
    try:
        parts = parts[: parts.index(REPO_NAME) + 1]
    except ValueError:
        name = "/" + REPO_NAME
        parts = parts[: parts.index(name) + 1]

    return pathlib.Path("/".join(parts))


def threaded_scan(cidr_block="192.168.1.0/24", port=22, ttl=0.5):
    """
    Searches the network for devices listening on the specified port.
    """

    def scan_ip(ip, results):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(ttl)
        result = sock.connect_ex((ip, port))
        if result == 0:
            try:
                hostname = socket.gethostbyaddr(ip)[0]
            except socket.herror:
                hostname = None
            results.append((ip, hostname))
        sock.close()

    ips = ipaddress.ip_network(cidr_block).hosts()

    threads = []
    results = []
    for ip in ips:
        t = threading.Thread(target=scan_ip, args=(str(ip), results))
        threads.append(t)
        t.start()
    for t in threads:
        t.join()

    return results


def get_text(textfile: pathlib.Path) -> str:
    """
    Trivial little function that returns text file contents as a string.
    """
    with open(textfile, "r") as file:
        text = file.read()
    return text


def run_bash_script_and_return_results(
    script_filepath: pathlib.Path,
    script_args: list,
    error_code_flags: tuple | list,
    invert_bits: bool = False,
    progress_bar: dict = {},
) -> dict:
    """
    Runs a bash script and interprets the exit code bitwise to return a dict
    that outlines which error code flags were returned, if any.

    Parameters:
    -----------
    script_filepath : pathlib.Path
        the filepath to the script itself
    script_args : list[str]
        arguments to pass to the script
    error_code_flags : tuple | list
        a sequence of short names for each flag in the 8-bit error code,
        starting from bit 0
    inverse_bits : bool, default False
        as the name suggests, does a bitwise NOT on the error code before
        converting to a dict; this can sometimes come in handy if you want
        your error_code_flags to be "positive" (e.g., "test_passed")
    progress_bar : dict, default {}
        a dict storing the kwargs to pass to Rich's Progress class, by
        default an empty dict, which means no progress bar will be shown.
        OPTIONS:
            - "total" : int, default 100
                the total number of steps to completion
            - "task" : str, default "Running..."
                the text to display next to the progress bar
            - "color" : str, default "white"
                the color of the progress bar

    Returns:
    --------
    dict
        A dictionary of form {error_code_flag: bool}

    """
    # store args and kwargs going to the command that runs the bash script
    run_args = [str(script_filepath)] + script_args
    run_kwargs = {"text": True}

    try:
        if progress_bar:
            # get options from param
            total = progress_bar.get("total", None)
            task_title = progress_bar.get("task", "Running...")
            color = progress_bar.get("color", "white")

            with Progress(transient=True) as progress:
                task = progress.add_task(f"[{color}]{task_title}", total=total)

                process = subprocess.Popen(
                    run_args,
                    **run_kwargs,
                )

                while not progress.finished:
                    if process.poll() is not None:
                        progress.update(task, completed=100)
                        break

                exit_code = process.wait()
                permission_to_run = True
        else:
            # call the script and get the exit code
            result = subprocess.run(run_args, capture_output=True, **run_kwargs)
            exit_code = result.returncode
            permission_to_run = True

    except PermissionError:
        exit_code = 2 ** len(error_code_flags) - 1
        permission_to_run = False

    # invert exit code bits if requested
    if invert_bits:
        exit_code = ~exit_code

    # interpret the exit code as a bitmask
    check_results = {}
    for i, check in enumerate(error_code_flags):
        check_results[check] = (exit_code & (1 << i)) != 0

    # add permission predicate run outside of script
    # (this seems funky, but it's so you can quickly check for success/failure
    # by using something like `all(check_results.values())`)
    if invert_bits:
        check_results["permission_ok"] = permission_to_run
    else:
        check_results["permission_error"] = not permission_to_run

    return check_results


if __name__ == "__main__":
    print(get_tracr_root())
