import json
import uuid
import paramiko
from pathlib import Path


CONFIG_DIR_FP = Path("~/.config/tracr/")
PROJECT_ROOT = Path(__file__).parent.parent.absolute()


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

    Attributes:
    -----------
    controller_config_fp : Path
        The path to the controller config file, which is not expanded to the user's home directory.

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

    controller_config_fp = CONFIG_DIR_FP / "controller_config.json"

    def __init__(self, make_new_config_file=False):
        self.controller_config_path = self.controller_config_fp.expanduser()
        if not self.controller_config_path.exists():
            if make_new_config_file:
                self.create_new_controller_config()
            else:
                raise FileNotFoundError(
                    f"Controller config file not found at {str(self.controller_config_path)}. "
                )
        with open(
            PROJECT_ROOT / "setup" / "default_controller_config.json", "r"
        ) as file:
            self.default_controller_config = json.load(file)

    @classmethod
    def config_file_exists_locally(cls) -> bool:
        """
        Returns True if the controller config file exists locally.
        """
        return Path(cls.controller_config_fp).expanduser().exists()

    @classmethod
    def erase_local_config_file(cls):
        """
        Erases the local controller config file.
        """
        Path(cls.controller_config_fp).expanduser().unlink(missing_ok=True)

    def create_new_controller_config(self):
        self.controller_config_path.parent.mkdir(parents=True, exist_ok=True)
        self.controller_config_path.touch()
        with open(
            PROJECT_ROOT / "setup" / "default_controller_config.json", "r"
        ) as file:
            default = json.load(file)
        default["controller"]["uuid"] = str(uuid.uuid4())
        with open(self.controller_config_path, "w") as file:
            json.dump(default, file, indent=4, sort_keys=True)

    def edit_config_item(self, item: str, new_value: str, category: str = None):
        """
        Edits the given item in the local config file

        Parameters:
        -----------
        item: str
            The item to edit in the device config file.
        new_value: str
            The new value to assign to the given item.
        category: str, optional
            The category to edit in the device config file.
        """

        if not ControllerConfigs().config_file_exists_locally():
            raise FileNotFoundError("Device config file not found. ")

        # read the config file
        with open(self.controller_config_path, "r") as f:
            config = json.load(f)

        # store a copy in case something goes wrong
        backup = config.copy()

        # edit the config file
        if isinstance(new_value, Path):
            new_value = str(new_value.expanduser().absolute())
        if category:
            config[category][item] = new_value
        else:
            config[item] = new_value

        # try to write the config file, or revert to the backup if something goes wrong
        try:
            with open(self.controller_config_path, "w") as f:
                json.dump(config, f, indent=4, sort_keys=True)
        except Exception as e:
            with open(self.controller_config_path, "w") as f:
                json.dump(backup, f, indent=4, sort_keys=True)
            raise e

    def get_known_devices(self, copy=True) -> list:
        """
        Returns a list of known devices from the controller config file.
        """
        with open(self.controller_config_path, "r") as file:
            config = json.load(file)
        # fresh config files come with a blank device, so check for that
        known_devs = config["known_devices"]
        if len(known_devs) == 1 and not known_devs[0].get("uuid", ""):
            return []
        return known_devs

    def get_known_macs(self) -> list:
        """
        Returns a list of known devices from the controller config file.
        """
        known_devs = self.get_known_devices()
        return [ni["mac"] for dev in known_devs for ni in dev["network_interfaces"]]

    def get_known_device_info(self, id: uuid.UUID) -> dict:
        """
        Returns a dict representing the known device with the given UUID.
        """
        known_devices = self.get_known_devices()
        if isinstance(id, str):
            id = uuid.UUID(id)
        for device in known_devices:
            if uuid.UUID(device["uuid"]) == id:
                return device
        return None

    def edit_known_device(self, id: uuid.UUID, param: str, new_value: str):
        """
        Edits the value of a key in a known device dict.
        """
        if isinstance(id, str):
            id = uuid.UUID(id)
        kd_info = self.get_known_device_info(id)

        # control which parameters can be in the config
        if not param in kd_info.keys():
            if self.debug:
                raise KeyError(f"Parameter {param} not found in known device {id}. ")
            else:
                return False

        # update the value of the chosen param
        kd_info[param] = new_value

        # load known devices into memory as list, then replace the one we're editing
        current_kds = self.get_known_devices()
        for i, device in enumerate(current_kds):
            if uuid.UUID(device["uuid"]) == id:
                current_kds[i] = kd_info
                break

        # save the updated known devices list to the config file
        self.set_known_devices(current_kds)
        return True

    def add_known_device(self, new_device: dict):
        """
        Adds a new known device to the controller config file.
        """
        default = self.default_controller_config["known_devices"][0]
        for newkey, newval in new_device.items():
            if newkey not in default.keys():
                raise KeyError(f"Key {newkey} not found in default known device. ")
            if not isinstance(newval, type(default[newkey])):
                raise TypeError(
                    f"Value {newval} is not of type {type(default[newkey])}. "
                )
            if newkey == "network_interfaces":
                if len(newval):
                    for ni_dict in newval:
                        for ni_key, ni_val in ni_dict.items():
                            if ni_key not in default["network_interfaces"][0].keys():
                                raise KeyError(
                                    f"Key {ni_key} not found in default network interface. "
                                )
                            if not isinstance(
                                ni_val, type(default["network_interfaces"][0][ni_key])
                            ):
                                raise TypeError(
                                    f"Value {ni_val} is not of type {type(default['network_interfaces'][0][ni_key])}. "
                                )
                else:
                    newval = default["network_interfaces"]
        for dkey, dval in default.items():
            if dkey not in new_device.keys():
                if dkey == "uuid":
                    raise KeyError(f"Key {dkey} not found in new device. ")
                new_device[dkey] = dval

        current_kds = self.get_known_devices()
        current_kds.append(new_device)
        self.set_known_devices(current_kds)

    def set_known_devices(self, new_known_devices: list):
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
        self.device_config_path = CONFIG_DIR_FP / "device_config.json"
        with open(PROJECT_ROOT / "setup" / "default_device_config.json", "r") as file:
            self.default_device_config = json.load(file)

    def get_expanded_config_fp(self, ssh_client: paramiko.SSHClient) -> Path:
        """
        Returns the expanded file path of the device config file on the remote device.

        Parameters:
        -----------
        ssh_client: paramiko.SSHClient
            The SSH client to use to connect to the remote device.
        """
        fp = str(self.device_config_path.parent)
        stdin, stdout, stderr = ssh_client.exec_command(f"echo {fp}")
        expanded = stdout.read().decode().strip()
        return Path(expanded) / self.device_config_path.name

    def get_stored_device_configs(self, ssh_client: paramiko.SSHClient):
        """
        Returns a dict representing the device's saved info in its JSON configs
        """
        if not remote_file_exists(ssh_client, self.device_config_path):
            return False
        return get_remote_file_contents(
            ssh_client, self.device_config_path, as_type="json"
        )

    def create_new_device_config(
        self, ssh_client: paramiko.SSHClient, force: bool = False
    ):
        """
        If the device config file does not exist, creates a new device config file
        with the default values (blank).

        Parameters:
        -----------
        ssh_client: paramiko.SSHClient
            The SSH client to use to connect to the remote device.
        force: bool
            A flag to force the creation of a new device config file, even if one
            already exists.
        """
        self.controller_config_path.parent.mkdir(parents=True, exist_ok=True)
        self.controller_config_path.touch()
        # if the file already exists, and we're not forcing a new one
        if not force and self.get_stored_device_configs(ssh_client):
            raise FileExistsError("Device config file already exists. ")

        expanded_fp = self.get_expanded_config_fp(ssh_client)

        # create the tracr config directory if it doesn't exist
        stdin, stdout, stderr = ssh_client.exec_command(
            f"mkdir -p {str(expanded_fp.parent)}"
        )
        if stdout.channel.recv_exit_status() != 0:
            raise OSError(
                f"Could not create tracr config directory: {stderr.read().decode()}"
            )

        # touch the device config file
        stdin, stdout, stderr = ssh_client.exec_command(f"touch {str(expanded_fp)}")
        if stdout.channel.recv_exit_status() != 0:
            raise OSError(
                f"Could not create device config file: {stderr.read().decode()}"
            )

        # create a UUID for the device and add it to the default config
        device_uuid = str(uuid.uuid4())
        this_config = self.default_device_config.copy()
        this_config["uuid"] = device_uuid

        # finally, use sftp to write the config to the file
        try:
            with ssh_client.open_sftp() as sftp:
                with sftp.open(str(expanded_fp), "w") as file:
                    json.dump(this_config, file, indent=4, sort_keys=True)
        except Exception as e:
            raise OSError(f"Could not write to device config file: {e}")

    def get_stored_macs(self, ssh_client: paramiko.SSHClient) -> list:
        """
        Returns a list of the MAC addresses found in the remote device's
        config file.

        Parameters:
        -----------
        ssh_client: paramiko.SSHClient
            The SSH client to use to connect to the remote device.

        Returns:
        --------
        list
            A list of the MAC addresses found in the remote device's config file.
        """
        configs = self.get_stored_device_configs(ssh_client)
        if not configs:
            raise FileNotFoundError("Device config file not found. ")
        net_interfaces = [ni for ni in configs["network_interfaces"] if ni["mac"]]
        if not len(net_interfaces):
            return []
        return [ni["mac"] for ni in net_interfaces]

    def get_uuid(self, ssh_client: paramiko.SSHClient) -> uuid.UUID:
        """
        Returns the UUID of the remote device.

        Parameters:
        -----------
        ssh_client: paramiko.SSHClient
            The SSH client to use to connect to the remote device.

        Returns:
        --------
        uuid.UUID
            The UUID of the remote device.
        """
        configs = self.get_stored_device_configs(ssh_client)
        if not configs:
            raise FileNotFoundError("Device config file not found. ")
        return uuid.UUID(configs["uuid"])

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
            if "fp" in item:
                return Path(contents[item])
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

            # store a copy in case something goes wrong
            backup = config.copy()

            # edit the config file
            if isinstance(new_value, Path):
                new_value = str(new_value.expanduser().absolute())
            config[item] = new_value

            # try to write the config file, or revert to the backup if something goes wrong
            try:
                with sftp.file(self.device_config_path, "w") as f:
                    json.dump(config, f, indent=4, sort_keys=True)
            except Exception as e:
                with sftp.file(self.device_config_path, "w") as f:
                    json.dump(backup, f, indent=4, sort_keys=True)
                raise e


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
