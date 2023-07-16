import json
import subprocess
import pathlib
import shutil
import oyaml as yaml

import api.utils as utils
from api.exceptions import ExperimentNameConflictException


class Config:
    """
    Parent class for ExperimentConfig and possibly other config classes
    later on.
    """

    filepath: pathlib.Path
    default_template: dict
    default_filename: str

    @classmethod
    def create_new(cls, target_dir: pathlib.Path):
        """
        Creates a new config file in the specified directory.

        Parameters
        ----------
        target_dir : pathlib.Path
            The directory in which to create the new config file.

        Returns
        -------
        config : Config
            The new config object.
        """
        if not target_dir.exists():
            raise ValueError(f"Invalid target directory: {target_dir}")
        else:
            # touch the file
            save_to = target_dir / cls.default_filename
            if save_to.exists():
                save_to.touch()

            # and put empty yaml in it
            with open(save_to, "w") as f:
                yaml.safe_dump({}, f)

            # now we can initialize the config object and let it finish
            config = cls(target_dir / cls.default_filename)
            config.save(config.default_template)
            return config

    def __init__(self, fp: pathlib.Path):
        self.filepath = fp
        if not (
            self.filepath.exists()
            and self.filepath.is_file()
            and self.filepath.suffix == ".yaml"
        ):
            raise ValueError(f"No config file found at {fp}")
        else:
            try:
                with open(self.filepath, "r") as f:
                    _ = yaml.safe_load(f)
            except Exception as e:
                raise ValueError(f"Error loading config file at {fp}: {e}")

    def load(self) -> dict:
        with open(self.filepath, "r") as f:
            return yaml.safe_load(f)

    def save(self, data):
        with open(self.filepath, "w") as f:
            yaml.safe_dump(data, f)

    def getval(self, *keys):
        data = self.load()
        for key in keys:
            try:
                data = data[key]
            except KeyError:
                return None
        return data

    def setval(self, *keys, value=None):
        if not value:
            raise ValueError("'value' kwarg must be specified")
        data = self.load()
        for key in keys[:-1]:
            try:
                data = data[key]
            except KeyError:
                raise ValueError(f"Invalid key: {key}")

        data[keys[-1]] = value
        self.save(data)


class ExperimentConfig(Config):
    """
    Represents the experimentconfig.yaml file in an experiment directory.
    """

    default_template = {
        "meta": {
            "name": "",
            "date_created": "",
            "last_modified": "",
        },
        "datasets": {
            "directory": "Datasets",
        },
        "models": {
            "directory": "Models",
        },
        "output": {
            "directory": "Output",
        },
        "nodes": {
            "directory": "NodeTypes",
            "types": {
                "Client": {
                    "depends_on": "Server",
                    "environment": {
                        "python_version": "3.8.17",
                        "pip_version": "21.3.1",
                    },
                    "accepted_args": [],
                    "main_file": "main.py",
                    "requires_gpu": False,
                    "uses_gpu": False,
                    "supported_cpu_architectures": ["x86_64", "arm64"],
                    "min_ram_mb": 1000,
                    "supports_multiple_instances": True,
                    "grpc_port": 50051,
                },
                "Server": {
                    "depends_on": None,
                    "environment": {
                        "python_version": "3.8.17",
                        "pip_version": "21.3.1",
                    },
                    "accepted_args": [],
                    "main_file": "main.py",
                    "requires_gpu": False,
                    "uses_gpu": False,
                    "supported_cpu_architectures": ["x86_64", "arm64"],
                    "min_ram_mb": 1000,
                    "supports_multiple_instances": False,
                    "grpc_port": 50051,
                },
            },
        },
        "runtime": {
            "experiment_level_parameters": [],
        },
    }
    default_filename = "experimentconfig.yaml"

    def __init__(self, fp: pathlib.Path):
        super().__init__(fp)

        # TODO: check that directory structure matched file and fix if not


class Experiment:
    """
    The Experiment class represents a single experiment configured by the user.
    It's initialized with an absolute path to the experiment's directory, which
    should contain all the information necessary to construct an experiment
    instance, which should then be able to run the experiment with a variety of
    user-specified parameters.

    The basic structure of an experiment directory looks like this:

    .
    └── MyExperiment/
        ├── Models/
        │   ├── alexnet.pt
        │   └── vgg.pth
        ├── Datasets/
        │   ├── testset_as_directory/
        │   │   ├── hotdog.jpg
        │   │   ├── not_a_hotdog.jpg
        │   │   └── labels.txt
        │   ├── testset_as_file.csv
        │   └── testset_as_getter.py
        ├── Output/
        │   └── results_230709_113044.csv
        ├── NodeTypes/
        │   ├── Type1/
        │   │   ├── main.py
        │   │   ├── src/
        │   │   │   ├── module1.py
        │   │   │   └── module2.py
        │   │   ├── requirements.txt
        │   │   ├── type1-venv/
        │   │   ├── .python-version
        │   └── Type2/
        │       └── ...
        ├── README.md
        └── experimentconfig.yaml

    Models/ (directory)
    -------------------
        Contains all the models available for use in the experiment,
        stored as PyTorch .pt or .pth files.

    Datasets/ (directory)
    ---------------------
        Contains all the datasets available for use in the experiment,
        stored as one of the following:
            - a directory of files along with a labels.txt
              or labels.csv file
            - a single file containing all the data, (tabular data)
            - a python script that returns a dataset in one of the
              above formats (e.g. a script that downloads a dataset)

    Output/ (directory)
    -------------------
        Contains all the output files generated by the experiment.

    NodeTypes/ (directory)
    ----------------------
        Contains subdirectories outlining the different types of nodes
        available for use in the experiment (e.g., "Client", "Server").
        Each subdirectory contains the following components:
            - main.py
                The main runtime script for the node.
            - src/ (directory)
                A directory containing all the custom modules used by
                the node.
            - requirements.txt
                A list of dependencies for the node, which will be used
                to create a virtual environment for the node.
            - .python-version
                A file containing the python version to use for the
                node's virtual environment.

    README.md
    ---------
        A markdown file containing a description of the experiment.
        When an experiment directory is first created, this file contains
        a template for the user to fill out, as well as a description of
        the experiment's directory structure, much like this one.

    experimentconfig.yaml
    ---------------------
        A file containing the experiment's configuration, which can be
        modified by the user.

    Note that participating devices must have the following dependencies
    installed to properly run experiments:
        pyenv
            allows the experiment to enforce a specific python version
        venv
            allows the experiment to create a virtual environment on the
            device
    """

    name: str
    root: pathlib.Path
    main_config: ExperimentConfig
    models: "dict[str, pathlib.Path]"
    datasets: "dict[str, pathlib.Path]"
    output: "dict[str, pathlib.Path]"
    readme: "dict[str, pathlib.Path]"
    node_types: "dict[str, dict]"

    def __init__(self, experiment_dir: pathlib.Path):
        # Catch bad input
        self.root = experiment_dir
        if not isinstance(self.root, pathlib.Path):
            self.root = pathlib.Path(experiment_dir)
        if not self.root.exists():
            raise ValueError(f"Experiment directory does not exist: {experiment_dir}")
        if not self.root.is_dir():
            raise ValueError(
                f"Experiment directory is not a directory: {experiment_dir}"
            )

        self.name = experiment_dir.name

        # Config file tells us where to find the rest of the experiment
        self.main_config = ExperimentConfig(self.root / "experimentconfig.yaml")

        # Store a dict of each model's filename, path
        model_dir = self.root / self.main_config.getval("models", "directory")
        self.models = {path.name: path for path in model_dir.glob("*.pt*")}

        # Store datasets similarly
        dataset_dir = self.root / self.main_config.getval("datasets", "directory")
        self.datasets = {path.name: path for path in dataset_dir.glob("*")}

        # Same with output files
        output_dir = self.root / self.main_config.getval("output", "directory")
        self.output = {path.name: path for path in output_dir.glob("*")}

        # README.md is just stored as a pathlib.Path
        self.readme = self.root / "README.md"

        # Node types are just a direct reference to the "nodes" section of the
        # experiment config
        self.node_types = self.main_config.getval("nodes", "types")

    def run(self, **parameters):
        # parse params
        if "run_local" in parameters:
            run_local = bool(parameters["run_local"])

        # if run_local is true, run the experiment locally
        if run_local:
            pass


class Launcher:
    """
    The Launcher class
    """


class ExperimentManager:
    """
    Manages a collection of experiments, allowing the user to create new
    experiments, run existing experiments, view the results of past
    experiments, and edit the configuration of existing experiments.
    """

    experiments: "list[Experiment]"
    experiment_dir: pathlib.Path

    def __init__(self, experiment_dir: pathlib.Path):
        # Catch bad input
        self.experiment_dir = experiment_dir
        if not isinstance(self.experiment_dir, pathlib.Path):
            self.experiment_dir = pathlib.Path(experiment_dir)
        if not self.experiment_dir.exists():
            raise ValueError(f"Experiment directory does not exist: {experiment_dir}")
        if not self.experiment_dir.is_dir():
            raise ValueError(
                f"Experiment directory is not a directory: {experiment_dir}"
            )

        # try loading each experiment
        self.experiments = []
        exps = [e for e in self.experiment_dir.glob("*") if e.is_dir()]
        for e in exps:
            try:
                self.experiments.append(Experiment(e))
            except Exception:
                print(f"Failed to load experiment {e.name}")

    def create_new_experiment(self, name: str, **kwargs):
        if " " in name:
            name = name.title().replace(" ", "")

        # Check that the experiment doesn't already exist
        if name in self._get_exp_names():
            raise ExperimentNameConflictException(f"Experiment {name} already exists")

        # Create the experiment directory
        exp_dir = self.experiment_dir / name
        exp_dir.mkdir()

        # Create the experiment config file and the README.md outline
        expconfig = ExperimentConfig.create_new(exp_dir)
        # get directory of file containing this function
        this_dir = pathlib.Path(__file__).parent
        if not this_dir.name == "api" and this_dir.name == "RACR_AI":
            this_dir = this_dir / "api"
        try:
            shutil.copyfile(
                this_dir / "Data" / "experiment_outline.md", exp_dir / "README.md"
            )
        except OSError:
            raise OSError("Failed to copy README.md template")

        # Create the subdirectories
        for exp_subcomponent in ["models", "datasets", "output", "nodes"]:
            (exp_dir / expconfig.getval(exp_subcomponent, "directory")).mkdir()

        # Finally, create the sub-subdirectories for default node types
        for name, info in expconfig.getval("nodes", "types").items():
            ndir = exp_dir / expconfig.getval("nodes", "directory") / name
            ndir.mkdir()
            (ndir / "src").mkdir()
            (ndir / "src" / "__init__.py").touch()
            (ndir / "requirements.txt").touch()
            (ndir / "main.py").touch()
            (ndir / ".python-version").touch()

            # Create a virtual environment in the directory
            subprocess.run(["python3", "-m", "venv", f"{name.lower()}_venv"], cwd=ndir)

            # Add the .python-version file to the dir so pyenv can enforce
            # the correct python version
            pversion = info.get("environment").get("python_version")
            subprocess.run(["pyenv", "install", "-s", pversion], cwd=ndir)
            subprocess.run(["pyenv", "local", pversion], cwd=ndir)

        # Now we can add the experiment to the collection
        try:
            self.experiments.append(Experiment(exp_dir))
        except Exception:
            print(f"Failed to load experiment {exp_dir.name} after creation.")

    def remove_experiment(self, name: str):
        # Check that the experiment exists
        if name not in self._get_exp_names():
            print(f"Experiment {name} does not exist - nothing to remove")

        if input(f"Are you sure you want to remove {name}? (y/n) ").lower() == "y":
            # Remove the experiment directory
            shutil.rmtree(self.experiment_dir / name)

            # Remove the experiment from the collection
            self.experiments = [e for e in self.experiments if e.name != name]

    def _get_exp_names(self) -> "list[str]":
        return [e.name for e in self.experiments]

    def run_experiment(self, name, parameters):
        for experiment in self.experiments:
            if experiment.name == name:
                experiment.run(parameters)


if __name__ == "__main__":
    manager = ExperimentManager(utils.get_tracr_root() / "TestCases")
    if "TestExperiment" not in manager._get_exp_names():
        manager.create_new_experiment("TestExperiment")
    else:
        manager.remove_experiment("TestExperiment")
