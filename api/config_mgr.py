import json
from pathlib import Path


CONFIG_PATH = Path("~/.config/tracr/").expanduser()
PROJECT_ROOT = Path(__file__).parent.parent.absolute()


class Configs:
    """
    A class that handles retrieving, editing, and saving data
    to/from various config files.
    """

    def __init__(self, make_controller_config=False):
        self.controller_config_path = CONFIG_PATH / "controller_config.json"
        if not self.controller_config_path.exists():
            if make_controller_config:
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
            json.dump(default, file)


if __name__ == "__main__":
    c = Configs(make_controller_config=True)
