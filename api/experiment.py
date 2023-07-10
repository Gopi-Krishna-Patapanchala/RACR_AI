import json
import pathlib


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
        │   │   ├── venv
        │   │   ├── requirements.txt
        │   │   ├── .python-version
        │   │   └── nodeconfig.yaml
        │   └── Type2/
        │       └── ...
        ├── README.md
        └── experimentconfig.yaml

    Note that participating devices must have the following dependencies
    installed to properly run experiments:
        pyenv
            allows the experiment to enforce a specific python version
        venv
            allows the experiment to create a virtual environment on the
            device
    """

    def __init__(self, name, code_dir, config):
        self.name = name
        self.code_dir = code_dir
        self.config = config

    def run(self, parameters):
        pass  # Implement experiment running


class ExperimentManager:
    def __init__(self):
        self.experiments = []

    def create_experiment(self, name, code_dir, config):
        experiment = Experiment(name, code_dir, config)
        self.experiments.append(experiment)

    def run_experiment(self, name, parameters):
        for experiment in self.experiments:
            if experiment.name == name:
                experiment.run(parameters)
