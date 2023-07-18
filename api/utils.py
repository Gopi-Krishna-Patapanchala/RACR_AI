import pathlib
import subprocess


def get_tracr_root() -> pathlib.Path:
    """
    Returns the root directory of the TRACR project as a pathlib.Path object.
    Does not matter where this function is called from, as long as it is
    called from within the TRACR project directory (which should be the case)
    """
    result = pathlib.Path(__file__).parent
    repeats = 0
    while result.name != "RACR_AI" and repeats < 5:
        result = result.parent
        repeats += 1
    return result


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

    Returns:
    --------
    dict
        A dictionary of form {error_code_flag: bool}

    """
    # call the script and get the exit code
    try:
        result = subprocess.run(
            [str(script_filepath)] + script_args, capture_output=True, text=True
        )
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
    check_results["permission_error"] = not permission_to_run

    return check_results


if __name__ == "__main__":
    print(get_tracr_root())
