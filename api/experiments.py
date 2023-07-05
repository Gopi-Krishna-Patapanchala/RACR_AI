import json
import os
import shutil
from pathlib import Path


EXPERIMENT_DIR_NAME = "TestCases"
CONFIG_FILE_NAME = "config.json"
SUMMARY_FILE_NAME = "experiment_outline.md"
CUSTOM_MODULE_DIR = "src"
SCRIPT_DIR = "Scripts"
DATA_DIR = "Datasets"
OUTPUT_DIR = "Output"


class Experiment:
    # evaluates to the location of the script that calls this module
    project_root = Path(__file__).parent.parent.absolute()

    def __init__(self):
        pass

    @classmethod
    def get_default_exp_config(cls) -> dict:
        """
        Returns the default configuration for a new experiment.

        Returns
        -------
        config : dict
            A dictionary containing the default configuration for a new
            experiment.
        """
        with open(cls.project_root / "setup" / "default_experiment_config.json") as f:
            config = json.load(f)
        return config

    @classmethod
    def add_new(cls, experiment_name: str) -> tuple:
        """
        Adds a new experiment to the controller's local system by setting up
        a 'blank slate' directory inside of TestCases.

        Parameters
        ----------
        experiment_name : str
            The name of the new experiment.

        Returns
        -------
        success, message : tuple[int, str]
            A tuple containing a success flag and a message.
        """

        if " " in experiment_name:
            experiment_name = experiment_name.title().replace(" ", "")
        test_cases_dir = cls.project_root / EXPERIMENT_DIR_NAME
        new_exp_dir = test_cases_dir / experiment_name

        if not test_cases_dir.exists():
            return 0, "No TestCases directory found."

        existing_experiment_names = [
            path.name for path in test_cases_dir.iterdir() if path.is_dir()
        ]

        if experiment_name in existing_experiment_names:
            return 0, f"Experiment '{experiment_name}' already exists."

        new_experiment_dir = test_cases_dir / experiment_name

        # Create new experiment directory
        try:
            os.makedirs(new_experiment_dir)
        except OSError:
            return 0, f"Creation of the directory {new_experiment_dir} failed."

        # Create the subdirectories
        dataset_dir = new_experiment_dir / DATA_DIR
        output_dir = new_experiment_dir / OUTPUT_DIR
        src_dir = new_experiment_dir / "src"

        for directory in (dataset_dir, output_dir, src_dir):
            os.makedirs(directory)

        # Create a config.json file
        config = Experiment.get_default_exp_config()
        try:
            with open(new_experiment_dir / CONFIG_FILE_NAME, "w") as f:
                json.dump(config, f, indent=4)
        except OSError:
            return 0, f"Creation of the config file failed."

        # Copy the default_outline.md to the new experiment directory
        try:
            shutil.copyfile(
                cls.project_root / "setup" / SUMMARY_FILE_NAME,
                new_experiment_dir / SUMMARY_FILE_NAME,
            )
        except OSError:
            return 0, f"Creation of the outline file failed."

        return 1, f"Experiment '{experiment_name}' successfully created."
