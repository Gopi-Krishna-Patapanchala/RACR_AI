import json
import getpass
import pathlib
import uuid
import paramiko
import logging
from contextlib import contextmanager

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

    setup_logging(3)  # DEBUG level

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
    remote_configs_dir = pathlib.Path("~/.config/tracr/")

    def __eq__(self, other):
        """
        Two devices are considered equal if they have the same UUID.
        """
        return self.id == other.id

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
        id: str
            The UUID of the device, as retrieved from the device itself or
            the controller device's known_devices file in `~/.config/tracr/.
            If not provided, the device will attempt to retrieve its UUID from
            the device itself. If this fails, a temporary UUID will be
            assigned.
        """
        logger.info(f"Creating Device object for {name}")

        self.name = name
        self.id = id
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

        # if the device has a temp uuid, set it to None and try to get the real one
        if self.id.startswith("temp"):
            logger.info(
                f"Device {name} has temporary UUID {self.id}. "
                + "Attempting to replace with real UUID."
            )
            self.id = None

        # convert id to UUID, or set to None if invalid
        if self.id and isinstance(self.id, str):
            try:
                self.id = uuid.UUID(self.id)
            except ValueError:
                logger.warning(
                    f"Invalid UUID {self.id} provided for device {name}"
                    + " - will attempt to retrieve UUID from device itself."
                )
                self.id = None

        # attempt to retrieve uuid from the device and compare to self.id
        try:
            expanded_path = self._expanduser_remote(
                Device.remote_configs_dir / "my_uuid.txt"
            )
            with self.open_sftp_file(expanded_path, "r") as f:
                uuid_str = f.read().decode().strip()
                uuid_obj = uuid.UUID(uuid_str)
                logger.info(
                    f"Successfully retrieved UUID {uuid_str} from device {name}."
                )

            # if the uuids don't match, use the one from the device
            if self.id and uuid_obj != self.id:
                logger.warning(
                    f"UUID {self.id} provided for device {name} "
                    + f"does not match UUID {uuid_str} on device. "
                    + "Using UUID from device."
                )
                self.id = uuid_obj

        except IOError as e:
            logger.warning(
                f"No file found at {expanded_path} on device {name}. "
                + f"Has this device been set up? Error: {e}"
            )
        except Exception as e:
            logger.info(f"Could not retrieve UUID from device {name}: {e}")

        # if we still don't have a valid uuid, generate a temporary one
        if not self.id:
            self.id = "temp" + str(uuid.uuid4())
            logger.info(f"Assigned temporary UUID {self.id} to device {name}.")

        logger.info(f"Device {name} created successfully.")
        logger.debug(f"Device {name} attributes: {self.__dict__}")

    @contextmanager
    def get_ssh_client(self):
        """
        Returns a paramiko SSHClient instance connected to the device. Most
        concise usage is:
            ```
            with device.get_ssh_client() as client:
                # Do stuff with client
            ```

        Returns:
        --------
        paramiko.SSHClient
        """
        client = paramiko.SSHClient()
        try:
            if isinstance(self.pkey, pathlib.Path) and self.pkey.expanduser().exists():
                client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                rsa_key = paramiko.RSAKey(filename=self.pkey.expanduser())
                logger.debug(
                    f"Using private key {self.pkey.expanduser()} to connect to device {self.name}."
                )
                client.connect(
                    self.host,
                    username=self.user,
                    pkey=rsa_key,
                )
                logger.info(f"Successfully connected to device {self.name} using pkey.")
            else:
                client.set_missing_host_key_policy(paramiko.WarningPolicy())
                pw = getpass.getpass(
                    f"\n\nEnter password for {self.user}@{self.host}: "
                )
                client.connect(
                    self.host,
                    username=self.user,
                    password=pw,
                    look_for_keys=False,
                    allow_agent=False,
                )
                logger.info(
                    f"Successfully connected to device {self.name} using password."
                )
            yield client
        except Exception as e:
            logger.warning(f"Could not connect to device {self.name}: {e}")
            raise e
        finally:
            client.close()

    @contextmanager
    def open_sftp_file(self, remote_path: pathlib.Path, mode: str):
        """
        Uses SFTP to open a remote file on the device for reading or writing.
        Similarly to `get_ssh_client()`, the most concise usage is:
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
            The mode to open the file in. Must be one of "r", "w", or "a".

        Returns:
        --------
        paramiko.SFTPFile
        """
        ssh = self.get_ssh_client()
        try:
            sftp = ssh.open_sftp()
        except (IOError, paramiko.AuthenticationException, paramiko.SSHException) as e:
            logger.warning(f"Could not connect to device {self.name}: {e}")
            ssh.close()
            raise e
        else:
            try:
                file = sftp.file(str(remote_path), mode)
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
                    sftp.close()
                    ssh.close()

    def _expanduser_remote(self, path: pathlib.Path) -> pathlib.Path:
        """
        Small utility function that expands the "~" character in a path to
        match the remote user's home directory rather than the local user's.
        """
        expanded = pathlib.Path(str(path).replace("~", f"/home/{self.user}"))
        logger.debug(f"Device {self.name} expanded path {path} to {expanded}.")
        return expanded

    def assign_uuid(self, overwrite: bool = False):
        """
        Creates a new UUID for the device and saves it to the device's
        ~/.config/tracr/my_uuid.txt file.

        Parameters:
        -----------
        overwrite: bool
            If True, will overwrite the device's existing UUID. If False,
            will raise an exception if the device already has a UUID.
        """
        remote_config_filepath = self._expanduser_remote(Device.remote_configs_dir)
        try:
            with self.get_ssh_client() as ssh:
                with ssh.open_sftp() as sftp:
                    # Create the remote config directory if it doesn't exist
                    try:
                        sftp.stat(str(remote_config_filepath))
                    except IOError:
                        sftp.mkdir(str(remote_config_filepath))

                    # Check if the device already has a UUID
                    remote_uuid_filepath = remote_config_filepath / "my_uuid.txt"
                    try:
                        # if this line doesn't raise an error, the file exists
                        sftp.stat(str(remote_uuid_filepath))

                        # if we're not overwriting, set self.id to the existing UUID
                        if not overwrite:
                            logger.warning(
                                f"Device {self.name} already has a UUID at {remote_uuid_filepath}."
                            )
                            with sftp.file(str(remote_uuid_filepath), "r") as uuid_file:
                                try:
                                    uuid_from_file = uuid.UUID(
                                        uuid_file.read().decode().strip()
                                    )
                                except ValueError:
                                    logger.warning(
                                        f"Device {self.name} has a malformed UUID at {remote_uuid_filepath}."
                                    )
                                    return
                            if uuid_from_file != self.id:
                                logger.warning(
                                    f"UUID stored on device {self.name} does not match device instance. "
                                    + "Updating self.id to match device UUID."
                                )
                                self.id = uuid_from_file
                                logger.debug(
                                    f"Device {self.name} UUID is now {self.id}."
                                )
                            return

                        # if we are overwriting, disgustingly raise an error to reach the except block
                        # TODO: stop this from being disgusting
                        else:
                            raise IOError

                    # we end up here if the file doesn't exist
                    except IOError:
                        with sftp.file(str(remote_uuid_filepath), "w") as uuid_file:
                            if not (self.id and isinstance(self.id, uuid.UUID)):
                                self.id = uuid.uuid4()
                            uuid_file.write(str(self.id))
                            logger.info(
                                f"Assigned UUID {self.id} to device {self.name} at {remote_uuid_filepath}."
                            )
        except Exception as e:
            logger.warning(f"Could not assign UUID to device {self.name}: {e}")

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

    def is_available(self) -> bool:
        """
        Returns True if the device is available for connection, False otherwise.
        """
        try:
            with self.get_ssh_client() as ssh:
                return True
        except Exception:
            return False


class DeviceManager:
    """
    The DeviceManager class is responsible for managing the collection of
    known devices. It is responsible for maintaining the list of known devices
    and saving/loading them to/from a JSON file. It also maintains paramiko
    objects which control authentication and connection behavior.
    """

    # the path to the controller's config file directory
    config_dir = pathlib.Path("~/.config/tracr").expanduser()

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
        return None

    def add_device(self, name: str):
        """
        Adds a device from ~/.ssh/config to the list of known devices used by
        tracr. This means that the user must set up and add the device to their
        config file before it can be added to their known devices. The word
        "known" really means "known by tracr" in this case. If there is not a
        uuid stored on the device in `~/.config/tracr/my_uuid.txt`, one will be
        created and stored there.

        Parameters:
        -----------
        name: str
            The name of the device in ~/.ssh/config
        """
        dev_config = self.ssh_config.lookup(name)
        new_device = Device(name, dev_config)
        new_device.assign_uuid()

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

    def discover_devices(self):
        pass  # Implement device discovery

    def load_known_devices(self):
        """
        Populates self.devices with Device objects instantiated using data
        from the file at ~/.config/tracr/known_devices.json.
        """
        device_data = self.get_known_devices()
        self.devices = [
            Device(d["name"], self.ssh_config.lookup(d["name"]), id=d["id"])
            for d in device_data
        ]

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


if __name__ == "__main__":
    dm = DeviceManager()
    for device in dm.devices:
        print(
            f"Device: {device.name}"
            + f"\n  ID: {device.id}\n  "
            + f"Host: {device.host}\n  "
            + f"Available: {device.is_available()}\n"
        )
