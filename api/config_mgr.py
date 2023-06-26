import json
import paramiko
from pathlib import Path


CONTROLLER_CONFIG_FP = Path("~/.config/tracr/").expanduser()
PROJECT_ROOT = Path(__file__).parent.parent.absolute()
DEVICE_CONFIG_FP = Path("~/.config/tracr/device_config.json")


def remote_file_exists(ssh_client: paramiko.SSHClient, fp: Path) -> bool:
    """
    Returns True if the given file path exists on the remote device.

    Parameters:
    -----------
    ssh_client: paramiko.SSHClient
        The SSH client to use to connect to the remote device.
    fp: Path
        The file path to check for on the remote device.
    """
    # create an SFTP client
    sftp = ssh_client.open_sftp()

    try:
        sftp.stat(fp)
        sftp.close()
        return True
    except IOError as e:
        return False


def get_remote_file_contents(
    ssh_client: paramiko.SSHClient, fp: Path, as_type: str = "string"
):
    """
    Returns the contents of the given file path on the remote device.

    Parameters:
    -----------
    ssh_client: paramiko.SSHClient
        The SSH client to use to connect to the remote device.
    fp: Path
        The file path to check for on the remote device.
    as_type: str, optional
        The type to return the file contents as. Can be "string" or "json".
    """
    # create an SFTP client
    sftp = ssh_client.open_sftp()

    try:
        with sftp.file(fp, "r") as f:
            content = f.read()
        if as_type == "json":
            result = json.load(content)
        elif as_type == "string":
            result = content.decode()  # decode bytes to string
        else:
            result = content.decode()  # TODO: raise an error

        sftp.close()
        return result

    except IOError as e:
        return False


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
        self.controller_config_path = CONTROLLER_CONFIG_FP / "controller_config.json"
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

    def get_known_devices(self, copy=True) -> list:
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

    def get_known_device_by(self, search_param: str, value: str) -> dict:
        """
        Returns a dict representing the known device with the given search_param
        matching the given value.
        """
        known_devices = self.get_known_devices()
        for device in known_devices:
            if device[search_param] == value:
                return device
        return None

    def edit_known_device(self, id_key_value: tuple, change_key_value: tuple):
        """
        Edits the value of a key in a known device dict.
        """
        known_devices = self.get_known_devices()
        for device in known_devices:
            if device[id_key_value[0]] == id_key_value[1]:
                device[change_key_value[0]] = change_key_value[1]
                self.set_known_devices(known_devices)
                return

    def set_known_devices(self, new_known_devices: dict):
        """
        Sets the known devices in the controller config file to the given list of
        known devices.
        """
        with open(self.controller_config_path, "r") as file:
            config = json.load(file)
        backup = config.copy()
        config["known_devices"] = new_known_devices
        try:
            with open(self.controller_config_path, "w") as file:
                json.dump(config, file, indent=4, sort_keys=True)
        except Exception as e:
            with open(self.controller_config_path, "w") as file:
                json.dump(backup, file, indent=4, sort_keys=True)
            raise e


class DeviceConfigs:
    """
    A class that handles retrieving, editing, and saving data to/from
    config files on a remote device.
    """

    def __init__(self):
        self.device_config_path = DEVICE_CONFIG_FP

    @classmethod
    def get_stored_device_configs(cls, ssh_client: paramiko.SSHClient):
        """
        Returns a dict representing the device's saved info in its JSON configs
        """
        if not remote_file_exists(ssh_client, DEVICE_CONFIG_FP):
            return None
        return get_remote_file_contents(ssh_client, DEVICE_CONFIG_FP, as_type="json")

    def get_item_from_config(self, ssh_client: paramiko.SSHClient, item: str):
        """
        Returns the value of the given item from the device config file on the
        remote device.

        Parameters:
        -----------
        ssh_client: paramiko.SSHClient
            The SSH client to use to connect to the remote device.
        item: str
            The item to retrieve from the device config file.
        """
        contents = self.get_remote_file_contents(
            ssh_client, self.device_config_path, as_type="json"
        )
        if not contents:
            raise FileNotFoundError("Device config file not found. ")
        try:
            return contents[item]
        except KeyError:
            return None

    def edit_config_item(
        self, ssh_client: paramiko.SSHClient, item: str, new_value: str
    ):
        """
        Edits the given item in the device config file on the remote device.

        Parameters:
        -----------
        ssh_client: paramiko.SSHClient
            The SSH client to use to connect to the remote device.
        item: str
            The item to edit in the device config file.
        new_value: str
            The new value to assign to the given item.
        """

        if not self.remote_file_exists(ssh_client, self.device_config_path):
            raise FileNotFoundError("Device config file not found. ")

        # create an SFTP client
        with ssh_client.open_sftp() as sftp:
            # read the config file
            with sftp.file(self.device_config_path, "r") as f:
                config = json.load(f)

            # edit the config file
            config[item] = new_value

            # write the config file
            with sftp.file(self.device_config_path, "w") as f:
                json.dump(config, f, indent=4, sort_keys=True)


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
