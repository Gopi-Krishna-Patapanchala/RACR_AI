import os
from pathlib import Path


EXPERIMENT_DIR_NAME = "TestCases"
CONFIG_FILE_NAME = "config.toml"
SUMMARY_FILE_NAME = "experiment_guide.md"
CUSTOM_MODULE_DIR = "src"
SCRIPT_DIR = "Scripts"
DATA_DIR = "Data"
OUTPUT_DIR = "Output"


class Experiment:
    def __init__(self):
        pass

    @classmethod
    def add_new(cls, experiment_name: str) -> None:
        # evaluates to the location of the script that calls this module
        project_root = Path(__file__).parent.absolute()

        testcase_dir = project_root / EXPERIMENT_DIR_NAME
        new_exp_dir = testcase_dir / experiment_name
        new_exp_dir.mkdir()
