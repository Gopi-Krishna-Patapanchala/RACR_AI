import json
from pathlib import Path


CONFIG_PATH = Path("~/.config/tracr/").expanduser()
PROJECT_ROOT = Path(__file__).parent.parent.absolute()


class ControllerConfigs:
    """
    A class that handles retrieving, editing, and saving data to/from various config files.

    Parameters:
    -----------
    make_new_config_file : bool, optional
        A flag to create a new controller config file if it does not exist, by default False.

    Methods:
    --------
    __init__(self, make_new_config_file=False)
        Initializes the Configs class with the controller_config_path attribute.
        If the controller_config_path does not exist and make_new_config_file is True,
        a new controller config file is created. Otherwise, a FileNotFoundError is raised.
    create_new_controller_config(self)
        Creates a new controller config file and saves it to the controller_config_path.
        The default_controller_config.json file is used as a template.
    """

    def __init__(self, make_new_config_file=False):
        self.controller_config_path = CONFIG_PATH / "controller_config.json"
        if not self.controller_config_path.exists():
            if make_new_config_file:
                self.create_new_controller_config()
            else:
                raise FileNotFoundError("Controller config file not found. ")

    def create_new_controller_config(self):
        self.controller_config_path.parent.mkdir(parents=True, exist_ok=True)
        self.controller_config_path.touch()
        with open(
            PROJECT_ROOT / "setup" / "default_controller_config.json", "r"
        ) as file:
            default = json.load(file)
        with open(self.controller_config_path, "w") as file:
            json.dump(default, file, indent=4, sort_keys=True)

    def get_known_devices(self):
        """
        Returns a list of known devices from the controller config file.
        """
        with open(self.controller_config_path, "r") as file:
            config = json.load(file)
        # fresh config files come with a blank device, so check for that
        known_devs = config["known_devices"]
        if len(known_devs) == 1 and set(known_devs[0].values()) == {""}:
            return []
        return known_devs


class Configs:
    """
    Just a consolidator class for the other config classes.
    """

    def __init__(
        self, controller_config=None, device_config=None, experiment_config=None
    ):
        self.controller = controller_config
        self.device = device_config
        self.experiment = experiment_config


if __name__ == "__main__":
    c = Configs(controller_config=ControllerConfigs(make_new_config_file=True))
