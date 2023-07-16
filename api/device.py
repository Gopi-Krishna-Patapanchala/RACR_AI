import json
import getpass
import pathlib
import uuid
import paramiko
import logging
from contextlib import contextmanager

from api.exceptions import (
    DeviceNotSetupException,
    DeviceUnavailableException,
    MalformedUUIDException,
    MissingSetupException,
    UUIDExistsException,
    DeviceNameConflictException,
)

logger = logging.getLogger(__name__)

# Checks if the module is being run directly
if __name__ == "__main__":

    def setup_logging(verbosity):
        levels = [logging.ERROR, logging.WARNING, logging.INFO, logging.DEBUG]
        format = "%(asctime)s - %(module)s - %(levelname)s: %(message)s"
        logging.basicConfig(
            filename="app.log",
            level=levels[min(verbosity, len(levels) - 1)],
            format=format,
        )

    setup_logging(0)  # DEBUG level

    logger.debug("device.py run as main.")

else:
    logger.debug("device.py imported.")


class Device:
    """
    To instantiate a Device object, the Controller device must have the host
    set up in its `~/.ssh/config` file. Ideally, passwordless SSH should be
    configured, resulting in a config block that looks like this:
        ```
        Host <self.name>
            HostName <self.host>    # can use IP or hostname
            User <self.username>
            IdentityFile <self.pkey>
        ```
    However, it is also possible to use a password, although this is less
    secure and will require the user to enter their password every time they
    connect to the device. In this case, the config block must specify that
    public key authentication is disabled, resulting in a config block that
    looks like this:
        ```
        Host <self.name>
            HostName <self.host>    # can use IP or hostname
            User <self.username>
            PubkeyAuthentication no
        ```
    NOTE: Even if you've turned off public key authentication for this
    host, you still need to make sure that the SSH server is configured to
    allow password authentication. You can verify this by checking the
    `PasswordAuthentication` directive in the server's SSH configuration file
    (`/etc/ssh/sshd_config`). If it's set to `no`, you'll need to change it to
    `yes` and restart the SSH service.
    """

    # the directory where configs are stored on remote devices
    remote_configs_dir: pathlib.Path = pathlib.Path("~/.tracr/device_info")

    host: str  # IP address or hostname of the device
    user: str  # username to use when connecting to the device
    pkey: pathlib.Path  # path to private key file for the device
    id: uuid.UUID  # UUID of the device

    ssh: paramiko.SSHClient  # SSH client object used to connect to the device
    sftp: paramiko.SFTPClient  # SFTP client object used to interact with filesystem

    def __eq__(self, other):
        """
        Two devices are considered equal if they have the same UUID.
        """
        return self.id == other.id

    def __del__(self):
        """
        Closes the SSH and SFTP connections.
        """
        self.ssh.close()
        self.sftp.close()

    def __init__(self, name: str, config: paramiko.SSHConfigDict, id: str = ""):
        """
        Usually instantiated by the DeviceManager, Device objects use data
        parsed from the `~/.ssh/config` file on the Controller device to
        infer their attributes, then connect to the device to get its UUID,
        which is stored in a `~/.config/tracr/uuid.txt` file on the device.

        Parameters:
        -----------
        name: str
            The name of the device, as it appears in the `~/.ssh/config` file
            on the Controller device.
        config: paramiko.SSHConfigDict
            The config block for the device, as parsed from the
            `~/.ssh/config` file on the Controller device.
        id: str, default=""
            The UUID of the device, as retrieved from the device itself or
            the controller device's known_devices file in `~/.config/tracr/.
            The value can be an empty string, a "temp" uuid (the string "temp"
            + a real uuid string), or a real uuid string. If a real uuid string
            is not provided, the device will attempt to retrieve its UUID from
            the device itself. If this fails, a temporary UUID will be
            assigned.
        """
        logger.info(f"Creating Device object for {name}")

        self.name = name
        self.id = str(id)
        self.host = config.get("hostname")
        self.user = config.get("user")
        self.pkey = (
            pathlib.Path(config.get("identityfile")[0])
            if config.get("identityfile")
            else None
        )

        logger.info(
            f"Attributes assigned to Device {name} from SSHConfig: {self.__dict__}"
        )

        # warn the user if their config block is likely to cause problems
        if not self.pkey and config.get("pubkeyauthentication", "yes").lower() != "no":
            logger.warning(
                f"Device {name} has no private key, "
                + "but pubkey authentication is not disabled in ~/.ssh/config. "
                + "This may cause problems when connecting to the device."
            )

        # ESTABLISH SSH AND SFTP CONNECTIONS

        # create the SSH client object
        self.ssh = paramiko.SSHClient()
        self.ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            self._connect_to_ssh_client()
        except Exception as e:
            logger.warning(
                f"Device {name} could not connect to SSH client. " + f"Error: {e}"
            )

        # create the SFTP client object from the SSH client object
        # if ssh connection was successful (method handles errors)
        self._connect_to_sftp_client()

        # DEVICE ID VERIFICATION

        # if the device is unavailable, we can't do much verifying
        if not self.is_available():
            logger.warning(
                f"Device {name} is not available. " + "Will not attempt to verify UUID."
            )
            # if the provided uuid string is a valid UUID, assume it's correct
            try:
                self.id = uuid.UUID(self.id)
                return
            # and if it's not, assign a temporary UUID
            except ValueError:
                logger.warning(
                    f"Device {name} has invalid UUID {self.id}. "
                    + "Assigning a temp UUID instead."
                )
                self.id = "temp" + str(uuid.uuid4())
                return

        # check if the device has been set up, and do so if not
        if not self.is_setup():
            raise DeviceNotSetupException(
                f"Device {name} is not set up. "
                + "Please run `tracr device setup <NAME>` to set up the device."
            )

        # if the device wasn't initialized with a true UUID, make it None
        if self.id.startswith("temp") or self.id == "":
            logger.info(
                f"Device {name} has temporary UUID {self.id if self.id else 'None'}. "
                + "Attempting to replace with real UUID."
            )
            self.id = None

        # otherwise, attempt to convert the provided UUID to a UUID object
        else:
            try:
                self.id = uuid.UUID(self.id)
            except ValueError:
                raise MalformedUUIDException(
                    f"Invalid UUID {self.id} provided for device {name}"
                )

        # Now self.id is either None or a valid UUID object, so we will
        # ask the device for its true UUID to either confirm or replace it.
        remote_uuid = self.get_remote_uuid()
        if not remote_uuid:
            self._assign_uuid()
            remote_uuid = self.get_remote_uuid()

        # replace self.id if it does not match the remote UUID
        if self.id != remote_uuid:
            logger.warning(
                f"Device {name} has UUID {self.id} but remote UUID is {remote_uuid}. "
                + "Replacing local UUID with remote UUID."
            )
            self.id = remote_uuid

        logger.info(f"Device {name} created successfully.")
        logger.debug(f"Device {name} attributes: {self.__dict__}")

    def _connect_to_ssh_client(self):
        """
        Connects to the SSH client object.

        Raises:
        -------
        paramiko.ssh_exception.NoValidConnectionsError
            If the device is not reachable.
        paramiko.ssh_exception.AuthenticationException
            If the device rejects the credentials.
        """
        # options common to both connection methods
        connect_kwargs = {"username": self.user, "auth_timeout": 5}

        # if a private key is provided, use it
        if isinstance(self.pkey, pathlib.Path) and self.pkey.expanduser().exists():
            connection_method = "private key"
            rsa_key = paramiko.RSAKey(filename=self.pkey.expanduser())
            connect_kwargs.update({"pkey": rsa_key})

        # otherwise, use password authentication and disable agents & key lookups
        else:
            connection_method = "password"
            pw = getpass.getpass(f"\n\nEnter password for {self.user}@{self.host}: ")
            print("")
            connect_kwargs.update(
                {
                    "password": pw,
                    "look_for_keys": False,
                    "allow_agent": False,
                }
            )

        # attempt to connect to the device
        logger.info(
            f"Attempting to connect to device {self.name} using {connection_method}."
        )
        self.ssh.connect(self.host, **connect_kwargs)
        logger.info(
            f"Successfully connected to device {self.name} using {connection_method}."
        )

    def _connect_to_sftp_client(self):
        if self.is_available(client="ssh") and not self.is_available(client="sftp"):
            self.sftp = self.ssh.open_sftp()
            logger.info(f"Device {self.name} connected to SFTP client.")
        elif not self.is_available(client="ssh"):
            logger.warning(
                f"Device {self.name} is not available for SSH. "
                + "Will not attempt to connect to SFTP client."
            )

    @contextmanager
    def open_sftp_file(self, remote_path: pathlib.Path, mode: str):
        """
        Uses SFTP to open a remote file on the device for reading or writing.
        Designed to work like a local file, the most concise usage is:
            ```
            with device.open_sftp_file(remote_path, mode) as file:
                # Do stuff with file
            ```

        Parameters:
        -----------
        remote_path: pathlib.Path
            The path to the file on the device. Should not be absolute, as
            the "~" character will be expanded according to the remote user's
            home directory - not the local user's.
        mode: str
            The mode to open the file in. For instance, "r", "w", "a", or "x".

        Returns:
        --------
        paramiko.SFTPFile
        """
        try:
            file = self.sftp.file(str(remote_path), mode)
        except IOError as e:
            logger.warning(
                f"Could not open file {remote_path} on device {self.name}: {e}"
            )
            raise e
        else:
            logger.info(
                f"Opened file {remote_path} on device {self.name} in mode {mode}."
            )
            try:
                yield file
            finally:
                file.close()

    def is_setup(self) -> bool:
        """
        Returns True if the device is setup, False otherwise. A device is
        considered setup if it has a config directory at ~/.config/tracr.

        Returns:
        --------
        bool

        Raises:
        -------
        DeviceUnavailableException
            If the device is not available.
        """
        return self._remote_path_exists(Device.remote_configs_dir)

    def _expanduser_remote(self, path: pathlib.Path) -> pathlib.Path:
        """
        Small utility function that expands the "~" character in a path to
        match the remote user's home directory rather than the local user's.
        """
        expanded = pathlib.Path(str(path).replace("~", f"/home/{self.user}"))
        logger.debug(f"Device {self.name} expanded path {path} to {expanded}.")
        return expanded

    def get_remote_uuid(self) -> uuid.UUID | None:
        """
        Attempts to get the device's UUID from its ~/.config/tracr/my_uuid.txt
        file, returning None if the file does not exist.

        Returns:
        --------
        uuid.UUID | None

        Raises:
        -------
        DeviceUnavailableException
            If the device is not available.
        MissingSetupException
            If the device's config directory is missing
        MalformedUUIDException
            If the UUID file exists but does not contain a valid UUID.
        """
        # Raise an exception if the device is not available
        if not self.is_available():
            raise DeviceUnavailableException(
                f"Device {self.name} is not available. Cannot get UUID."
            )

        # Expand the remote path to match the remote user's home directory
        uuid_path = self._expanduser_remote(
            pathlib.Path(Device.remote_configs_dir / "my_uuid.txt")
        )

        # Check if the config directory exists on the device
        if not self._remote_path_exists(uuid_path.parent):
            raise MissingSetupException(
                f"Device {self.name} is missing its config directory. "
                + f"Cannot get UUID."
            )

        # Check if the UUID file exists on the device
        if not self._remote_path_exists(uuid_path):
            return None

        # Read the UUID file as string
        uuid_str = self._get_remote_file_contents(uuid_path).strip()

        # Attempt to convert the string to a UUID and return
        try:
            return uuid.UUID(uuid_str)
        except ValueError:
            raise MalformedUUIDException(
                f"Device {self.name} has a malformed UUID file. "
                + f"Cannot return UUID."
            )

    def _get_remote_file_contents(self, remote_path: pathlib.Path) -> str:
        """
        Reads the contents of a text file on the device and returns it as a
        string.

        Parameters:
        -----------
        remote_path: pathlib.Path
            The path to the file on the device. Should not be absolute, as
            the "~" character will be expanded according to the remote user's
            home directory - not the local user's.

        Returns:
        --------
        str

        Raises:
        -------
        DeviceUnavailableException
            If the device is not available.
        FileNotFoundError
            If the file does not exist on the device.
        """
        # Raise an exception if the device is not available
        if not self.is_available():
            raise DeviceUnavailableException(
                f"Device {self.name} is not available. Cannot get file contents."
            )

        # Expand the remote path to match the remote user's home directory
        true_path = self._expanduser_remote(remote_path)

        # Check if the file exists on the device
        if not self._remote_path_exists(true_path):
            raise FileNotFoundError(
                f"File {true_path} does not exist on device {self.name}."
            )

        # Read the file, decode, and return
        with self.open_sftp_file(true_path, "r") as file:
            return file.read().decode()

    def _remote_mkdir(self, remote_path: pathlib.Path):
        """
        Creates a directory on the device at the given path. If the directory
        already exists, does nothing.

        Parameters:
        -----------
        remote_path: pathlib.Path
            The path to the directory on the device. Should not be absolute,
            as the "~" character will be expanded according to the remote
            user's home directory - not the local user's.

        Raises:
        -------
        DeviceUnavailableException
            If the device is not available.
        """
        # Raise an exception if the device is not available
        if not self.is_available():
            raise DeviceUnavailableException(
                f"Device {self.name} is not available. "
                + f"Cannot create directory {remote_path}."
            )

        # Expand the remote path to match the remote user's home directory
        true_path = self._expanduser_remote(remote_path)

        # Create the directory, recursively creating parent dirs as needed
        try:
            parts = str(true_path).split("/")
            for i in range(len(parts)):
                current_path = "/".join(parts[: i + 1])
                try:
                    self.sftp.listdir(current_path)  # Test if path exists
                except IOError:  # Path does not exist
                    self.sftp.mkdir(current_path)
        except Exception as e:
            logger.warning(
                f"Could not create directory {true_path} on device {self.name}: {e}"
            )
            raise e
        else:
            logger.info(f"Created directory {true_path} on device {self.name}.")

    def _remote_path_exists(self, remote_path: pathlib.Path) -> bool:
        """
        Returns True if the given file or directory exists on the device, False
        otherwise.

        Parameters:
        -----------
        remote_path: pathlib.Path
            The path to the file or directory on the device. Should not be
            absolute, as the "~" character will be expanded according to the
            remote user's home directory - not the local user's.

        Returns:
        --------
        bool

        Raises:
        -------
        DeviceUnavailableException
            If the device is not available.
        """
        # Raise an exception if the device is not available
        if not self.is_available():
            raise DeviceUnavailableException(
                f"Device {self.name} is not available. "
                + f"Cannot check if path {remote_path} exists."
            )

        # Expand the remote path to match the remote user's home directory
        true_path = self._expanduser_remote(remote_path)

        # Check if the file or directory exists
        try:
            self.sftp.stat(str(true_path))
            return True
        except IOError:
            return False
        except Exception as e:
            logger.warning(
                f"Could not check if path {true_path} exists "
                + f"on device {self.name}: {e}"
            )
            raise e

    def _assign_uuid(self):
        """
        Creates a new UUID for the device and saves it to the device's
        ~/.config/tracr/my_uuid.txt file. To avoid conflicts, this method
        does not allow existing UUIDs to be overwritten.

        Raises:
        -------
        DeviceUnavailableException
            If the device is not available.
        MissingSetupException
            If the device is missing its config directory.
        """
        # Raise an exception if the device is not available
        if not self.is_available():
            raise DeviceUnavailableException(
                f"Device {self.name} is not available. Cannot assign UUID."
            )

        # get the path to the config dir on the device
        remote_config_dir = self._expanduser_remote(Device.remote_configs_dir)

        # Raise an exception if the device is missing its config directory
        if not self._remote_path_exists(remote_config_dir):
            raise MissingSetupException(
                f"Device {self.name} is missing its config directory. "
                + f"Cannot assign UUID."
            )

        # Write the my_uuid.txt file with "x" flag to prevent overwriting
        try:
            with self.open_sftp_file(remote_config_dir / "my_uuid.txt", "x") as f:
                f.write(str(uuid.uuid4()))
                logger.info(f"Assigned UUID to device {self.name}.")
        except OSError:
            raise UUIDExistsException(
                f"Device {self.name} already has a UUID. Cannot overwrite UUID."
            )

    def to_dict(self, type: str) -> dict:
        """
        Returns a dict representation of the device, suitable for saving to
        a certain JSON file, specified by the `type` parameter.

        Parameters:
        -----------
        type: str
            The type of dict to return. Currently only "known" is supported.
        """
        if type.strip().lower() == "known":
            result = {"name": self.name, "id": str(self.id)}

        # elif statements will go here to support more types

        else:
            raise ValueError(f"Unknown device dict type {type}.")

        logger.debug(f"Converted device {self.name} to dict: {result}")
        return result

    def is_available(self, client: str = "ssh") -> bool:
        """
        Returns True if the specified client is available, False otherwise.

        Parameters:
        -----------
        client: str, default "ssh"
            The client to check. Must be either "ssh" or "sftp".
        """
        client = client.strip().lower()
        if client == "ssh" or client == "sftp":
            try:
                self.ssh.exec_command("echo")
                if client == "sftp":
                    try:
                        self.sftp.listdir()
                        return True
                    except Exception:
                        return False
                return True
            except Exception:
                return False
        else:
            raise ValueError(
                "Device.is_available takes only"
                + f"'ssh' or 'sftp' as arguments, not {client}."
            )


class DeviceManager:
    """
    The DeviceManager class is responsible for managing the collection of
    known devices. It is responsible for maintaining the list of known devices
    and saving/loading them to/from a JSON file. It also maintains paramiko
    objects which control authentication and connection behavior.
    """

    # the path to the controller's config file directory
    config_dir = pathlib.Path("~/.tracr").expanduser()

    @classmethod
    def setup_controller(cls):
        """
        Sets up the controller device by creating a data subdirectory in the
        user's home directory.
        """
        cls.config_dir.mkdir(exist_ok=True)
        with open(cls.config_dir / "known_devices.json", "w") as file:
            json.dump({}, file)

    def __init__(self):
        self.devices = []
        self.known_device_filepath = DeviceManager.config_dir / "known_devices.json"

        self.ssh_config = paramiko.SSHConfig()
        with open(pathlib.Path("~/.ssh/config").expanduser(), "r") as ssh_config_file:
            self.ssh_config.parse(ssh_config_file)

        self.load_known_devices()

    def get_known_devices(self):
        """
        Returns a list of known device info dicts from the file at
        ~/.config/tracr/known_devices.json, or None if the file does not exist.

        Returns:
        --------
        list[dict] or None
        """
        try:
            with open(self.known_device_filepath, "r") as f:
                devices_data = json.load(f)
            logger.debug(
                f"Successfully retrieved known devices from {self.known_device_filepath}."
            )
            return devices_data
        except FileNotFoundError:
            logger.warning(
                f"No file found at {self.known_device_filepath}. "
                + "Has this device been set up?"
            )
            raise MissingSetupException(
                f"No file found at {self.known_device_filepath}. "
                + " To set up the controller, use `tracr setup`."
            )

    def add_device(self, name: str):
        """
        Adds a device from ~/.ssh/config to the list of known devices used by
        tracr. This means that the user must set up and add the device to their
        config file before it can be added to their known devices. The word
        "known" really means "known by tracr" in this case. If there is not a
        uuid stored on the device in `~/.config/tracr/my_uuid.txt`, one will be
        created (hopefully retrieved from the device itself) and stored there.

        Parameters:
        -----------
        name: str
            The name of the device in ~/.ssh/config
        """
        dev_config = self.ssh_config.lookup(name)

        # "lookup" returns a dict containing "hostname" : name for any name, so
        # we need to check that it's not missing something important
        if not dev_config.get("user"):
            logger.warning(
                f"No user specified in lookup for {name}. "
                + f"Please check your ~/.ssh/config file to ensure {name} is listed."
            )
            return

        new_device = Device(name, dev_config)

        known_devs = self.get_known_devices()
        known_ids = [d["id"] for d in known_devs]
        known_names = [d["name"] for d in known_devs]

        if new_device.id in known_ids or new_device.name in known_names:
            logger.warning(f"Device {name} is already in known devices.")
            return

        # make sure self.devices is up to date, then add the new device and save
        self.load_known_devices()
        self.devices.append(new_device)
        self.save_devices()

    def remove_device(self, name: str):
        """
        Removes a device from the self.devices list and the user's
        `~/.config/tracr/known_devices.json` file.

        Parameters:
        -----------
        name: str
            The name of the device to remove
        """
        matching_devs = self.get_devices_by(name=name)
        if len(matching_devs) == 0:
            logger.warning(f"No device found with name {name}. No device removed.")
            return
        elif len(matching_devs) > 1:
            raise DeviceNameConflictException(
                f"Multiple devices found with name {name}. Cannot remove device."
            )

        self.devices.remove(matching_devs[0])
        self.save_devices()

    def get_devices_by(self, **kwargs) -> list:
        """
        Returns filtered list of self.devices according to the key, value
        pairs specified in the kwargs. For example, if you want to get all
        devices with a certain user, you would call this function like so:
            ```
            get_devices_by(user="pi")
            ```
        You can also specify multiple kwargs, which will be ANDed together:
            ```
            get_devices_by(user="pi", hostname="raspberrypi")
            ```
        Finally, it is also valid to call this function using kwargs that
        correspond to parameterless methods with a return value, like so:
            ```
            get_devices_by(is_available=True)
            ```
        This will call the method `is_available` on each device and return
        only those for which it returns True.

        Parameters:
        -----------
        kwargs: dict
            The key, value pairs to filter the list of devices by.

        Returns:
        --------
        list[Device]

        Raises:
        -------
        ValueError
            If the kwargs are invalid.
        """
        result = self.devices

        for key, value in kwargs.items():
            new_result = []
            for device in result:
                if hasattr(device, key):
                    attr = getattr(device, key)
                    if callable(attr):
                        if attr() == value:
                            new_result.append(device)
                    elif attr == value:
                        new_result.append(device)
                else:
                    raise ValueError(f"Invalid key: {key}")
            result = new_result

        return result

    def discover_devices(self):
        pass  # Implement device discovery

    def load_known_devices(self):
        """
        Populates self.devices with Device objects instantiated using data
        from the file at ~/.config/tracr/known_devices.json.
        """
        device_data = self.get_known_devices()

        for d in device_data:
            try:
                device = Device(
                    d["name"], self.ssh_config.lookup(d["name"]), id=d["id"]
                )
                self.devices.append(device)
            except DeviceNotSetupException:
                logger.warning(
                    f"Device {d['name']} not set up. "
                    + "Use `tracr device setup <NAME>` to set up this device."
                )
                continue

    def save_devices(self):
        """
        Saves the current list of known devices to the file at
        ~/.config/tracr/known_devices.json.
        """
        devices_data = [device.to_dict("known") for device in self.devices]
        try:
            with open(DeviceManager.config_dir / "known_devices.json", "w") as f:
                json.dump(devices_data, f)
            logger.debug(
                f"Successfully saved known devices to {self.known_device_filepath}."
            )
        except FileNotFoundError:
            logger.warning(
                f"Could not save known devices to {self.known_device_filepath}."
            )


if __name__ == "__main__":
    # check controller setup
    if not (DeviceManager.config_dir / "known_devices.json").exists():
        DeviceManager.setup_controller()

    # check DeviceManager and Device instantiation
    dm = DeviceManager()

    # check reading known_devices.json, device filtering, adding, and removing,
    # then saving to known_devices.json, as well as both connection methods
    if dm.get_devices_by(name="home-pi-tracr"):
        dm.add_device("home-pi-tracr")
    else:
        dm.remove_device("home-pi-tracr")

    # check multi-parameter filtering
    if not dm.get_devices_by(name="home-pi-tracr"):
        dm.add_device("home-pi-tracr")
    assert (
        dm.get_devices_by(name="home-pi-tracr", is_available=True)[0].name
        == "home-pi-tracr"
    )

    for device in dm.devices:
        print(
            f"Device: {device.name}"
            + f"\n  ID: {device.id}\n  "
            + f"Host: {device.host}\n  "
            + f"Available: {device.is_available()}\n"
        )
