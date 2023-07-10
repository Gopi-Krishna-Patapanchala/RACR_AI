import pathlib


def get_tracr_root() -> pathlib.Path:
    result = pathlib.Path(__file__).parent
    repeats = 0
    while result.name != "RACR_AI" and repeats < 5:
        result = result.parent
        repeats += 1
    return result
