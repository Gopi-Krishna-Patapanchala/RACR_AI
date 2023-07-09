import json
import pathlib


class Experiment:
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
