import json
import rpyc
import numpy
import torch
import subprocess
import oyaml
import socket
import getpass
import pathlib
import uuid
import paramiko
import logging
import concurrent.futures
from rpyc.utils.zerodeploy import DeployedServer, MultiServerDeployment
from contextlib import contextmanager
from threading import Thread, Lock
from plumbum import SshMachine

import api.utils as utils
import api.bash_script_wrappers as bashw
from api.exceptions import (
    DeviceNotSetupException,
    DeviceUnavailableException,
    MalformedUUIDException,
    MissingSetupException,
    UUIDExistsException,
    DeviceNameConflictException,
)

logger = logging.getLogger("tracr_logger")

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
    container_ssh_dir: pathlib.Path = pathlib.Path("/host_ssh")
    name: str  # name of the device
    host: str  # IP address or hostname of the device
    user: str  # username to use when connecting to the device
    pkey: pathlib.Path  # path to private key file for the device
    pkey_dir: pathlib.Path = pathlib.Path(
        "/host_ssh"
    )  # path to directory containing private key file in container
    data_dir: pathlib.Path = pathlib.Path("~/.tracr")
    participant_module_dir: pathlib.Path = utils.get_tracr_root() / "ParticipantModule"
    permissions: tuple = ("744", "755")  # files, directories
    rpc_port: int = 9000  # port number for RPC server
    connected: bool = False  # whether or not the device is connected
    ssh: paramiko.SSHClient  # SSH client object used to connect to the device

    def __del__(self):
        """
        Closes the SSH and SFTP connections.
        """
        self.close_connections()

    def __init__(
        self, name: str, config: paramiko.SSHConfigDict, input_lock: Lock = None
    ):
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
        """
        logger.info(f"Creating Device object for {name}")

        self.name = name
        self.host = config.get("hostname")
        self.user = config.get("user")
        self.pkey = (
            self.pkey_dir / pathlib.Path(config.get("identityfile")[0]).name
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

        # create the SSH client object
        self.ssh = paramiko.SSHClient()
        self.ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        logger.info(f"Device {name} created successfully.")

        # connect to it
        try:
            self._connect_to_ssh_client(input_lock=input_lock)
        except paramiko.AuthenticationException:
            logger.warning(f"Device {name} rejected credentials.")
        except Exception as e:
            logger.info(f"Device {name} unavailable: {e}")

        logger.debug(f"Device {name} attributes: {self.__dict__}")

    def _connect_to_ssh_client(self, input_lock: Lock = None):
        """
        Connects to the SSH client object.

        Raises:
        -------
        paramiko.ssh_exception.NoValidConnectionsError
            If the device is not reachable.
        paramiko.ssh_exception.AuthenticationException
            If the device rejects the credentials.
        """
        # idempotent
        if self.connected and self.ssh_server_is_open():
            return

        # options common to both connection methods
        connect_kwargs = {"username": self.user, "auth_timeout": 2, "timeout": 2}

        # if a private key is provided, use it
        if isinstance(self.pkey, pathlib.Path) and self.pkey.expanduser().exists():
            connection_method = "private key"
            rsa_key = paramiko.RSAKey(filename=self.pkey.expanduser())
            connect_kwargs.update({"pkey": rsa_key})

        # otherwise, use password authentication and disable agents & key lookups
        else:
            connection_method = "password"

            def update_connect_kwargs(ckw):
                pw = getpass.getpass(
                    f"\n\nEnter password for {self.user}@{self.host}: "
                )
                print("")
                ckw.update(
                    {
                        "password": pw,
                        "look_for_keys": False,
                        "allow_agent": False,
                    }
                )

            if input_lock:
                with input_lock:
                    update_connect_kwargs(connect_kwargs)
            else:
                update_connect_kwargs(connect_kwargs)

        # attempt to connect to the device
        logger.info(
            f"Attempting to connect to device {self.name} using {connection_method}."
        )
        self.ssh.connect(self.host, **connect_kwargs)
        self.connected = True
        logger.info(
            f"Successfully connected to device {self.name} using {connection_method}."
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
            if self.connected:
                file = self.ssh.open_sftp().file(
                    str(self._expanduser_remote(remote_path)), mode
                )
            else:
                raise DeviceUnavailableException(
                    f"Cannot open file - Device {self.name} is not connected."
                )
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

    def run_ssh_command(self, command, success_message, failure_message):
        try:
            stdin, stdout, stderr = self.ssh.exec_command(command)
            return_code = stdout.channel.recv_exit_status()
            if return_code == 0:
                logger.info(success_message)
                return True
            else:
                logger.warning(failure_message)
                return False
        except Exception as e:
            logger.warning(f"{failure_message}: {e}")
            return False

    def as_ssh_machine(self):
        """
        Returns a plumbum SshMachine object that can be used to initialize a zero-deploy
        RPyC server on the device.
        """
        return SshMachine(self.host, user=self.user, keyfile=self.pkey)

    def setup(self):
        """
        Installs the participant module on the device and creates the data directory
        at ~/.tracr.
        """
        if not self.ssh_server_is_open():
            raise DeviceUnavailableException(
                f"Cannot setup device {self.name} - SSH server is not open."
            )
        if self.is_setup():
            logger.info(f"Device {self.name} is already set up.")
            return

        def update_results(results, key, status):
            results[key] = status

        results = {
            "data_dir": False,
            "copy_module": False,
            "prepare_apt": False,
            "install_packages": False,
            "install_pyenv": False,
            "configure_pyenv": False,
            "configure_venv": False,
        }

        # create the data directory
        try:
            self._remote_mkdir(self.data_dir)
            success = True
        except Exception as e:
            logger.warning(f"Could not create data directory: {e}")
            success = False
        update_results(results, "data_dir", success)
        logger.info(
            f"{'Created' if success else 'Failed to create'} data directory {self.data_dir} on device {self.name}."
        )

        # copy over the participant module and set permissions
        try:
            self.recursive_copy(
                self.participant_module_dir, self.data_dir / "ParticipantModule"
            )
            success = True
        except Exception as e:
            logger.warning(f"Could not copy participant module: {e}")
            success = False
        update_results(results, "copy_module", success)

        # Other actions
        update_results(results, "prepare_apt", self._prepare_apt())
        update_results(results, "install_packages", self._install_packages())
        update_results(results, "install_pyenv", self._install_pyenv())
        update_results(results, "configure_pyenv", self._configure_pyenv())
        update_results(results, "configure_venv", self._configure_venv())

        return results

    def _configure_venv(self):
        script_fp = (
            self.data_dir / "ParticipantModule" / "Scripts" / "configure_venv.sh"
        )
        return self.run_ssh_command(
            f"sudo {script_fp}",
            f"Configured virtual environment on device {self.name}.",
            f"Could not configure virtual environment on device {self.name}",
        )

    def recursive_copy(
        self,
        local_directory: pathlib.Path,
        remote_directory: pathlib.Path,
        dir_perms: int = 0o755,
        file_perms: int = 0o744,
    ):
        def sftp_copy(sftp, local_path, remote_path):
            # Create the remote directory including parents if not exists
            try:
                if not self._remote_path_exists(remote_path):
                    logger.debug(
                        f"Creating remote directory {remote_path} on {self.name}."
                    )
                    sftp.mkdir(str(remote_path), mode=dir_perms)
            except IOError:
                logger.debug(
                    f"Caught IOError when creating remote directory {remote_path} on {self.name}."
                )
                pass

            # Iterate through local directory
            for item in local_path.iterdir():
                remote_item = str(remote_path) + "/" + item.name
                logger.debug(f"Copying {item} to {remote_item} on {self.name}.")

                # Check if it's a file or directory
                if item.is_file():
                    logger.debug(
                        f"Copying file {item} to {remote_item} on {self.name}."
                    )
                    sftp.put(str(item), remote_item)
                    logger.debug(
                        f"Setting permissions on {remote_item} on {self.name}."
                    )
                    sftp.chmod(remote_item, mode=file_perms)
                    logger.info(f"Copied file {item} to {remote_item} on {self.name}.")

                elif item.is_dir():
                    logger.debug(f"Recursing into directory {item} on {self.name}.")
                    sftp_copy(sftp, item, remote_item)  # Recursively copy the directory

        if not self.ssh_server_is_open():
            raise DeviceUnavailableException(
                f"Cannot recursively copy to device {self.name} - SSH server is not open."
            )

        # expand user
        remote_directory = self._expanduser_remote(remote_directory)

        # Create the SFTP client
        logger.info(f"Opening SFTP client on device {self.name}.")
        sftp_client = self.ssh.open_sftp()

        # Create the root directory if it doesn't exist
        if not self._remote_path_exists(remote_directory):
            logger.debug(
                f"Creating remote directory {remote_directory} on {self.name} with permissions {oct(dir_perms)}."
            )
            sftp_client.mkdir(str(remote_directory), mode=dir_perms)
        else:
            logger.debug(
                f"Remote directory {remote_directory} already exists on {self.name}."
            )

        # Start the recursive copy
        sftp_copy(sftp_client, local_directory, remote_directory)

        # Close the SFTP client
        sftp_client.close()
        logger.info(f"Closed SFTP client on device {self.name}.")

    def _configure_pyenv(self):
        script_fp = (
            self.data_dir / "ParticipantModule" / "Scripts" / "configure_pyenv.sh"
        )
        return self.run_ssh_command(
            f"sudo {script_fp}",
            f"Configured pyenv on device {self.name}.",
            f"Could not configure pyenv on device {self.name}",
        )

    def _install_pyenv(self):
        script_fp = self.data_dir / "ParticipantModule" / "Scripts" / "install_pyenv.sh"
        return self.run_ssh_command(
            f"sudo {script_fp}",
            f"Installed pyenv on device {self.name}.",
            f"Could not install pyenv on device {self.name}",
        )

    def _install_packages(self):
        script_fp = (
            self.data_dir
            / "ParticipantModule"
            / "Scripts"
            / "install_participant_sys_deps.sh"
        )
        return self.run_ssh_command(
            f"sudo {script_fp}",
            f"Installed packages on device {self.name}.",
            f"Could not install packages on device {self.name}",
        )

    def _prepare_apt(self):
        script_fp = (
            self.data_dir
            / "ParticipantModule"
            / "Scripts"
            / "update_upgrade_clean_apt.sh"
        )
        return self.run_ssh_command(
            f"sudo {script_fp}",
            f"Prepared apt on device {self.name}.",
            f"Could not prepare apt on device {self.name}",
        )

    def is_setup(self, suppress=False) -> bool:
        """
        Returns True if the device is setup, False otherwise. A device is
        considered setup if its RPC server can be reached and calls are working
        as expected.

        Returns:
        --------
        bool
        """
        if not self.ssh_server_is_open():
            if suppress:
                return False
            else:
                raise DeviceUnavailableException(
                    f"Cannot validate setup - Device {self.name} is not available."
                )
        try:
            return self.rpc_mm_test()
        except Exception as e:
            if suppress:
                print(e)
                return False
            else:
                raise e

    def start_rpc_server(self, port: int = 9000):
        if not self.ssh_server_is_open():
            raise DeviceUnavailableException(
                f"Cannot start RPC server - Device {self.name} is not available."
            )
        stdin, stdout, stderr = self.ssh.exec_command(
            f"cd {self.data_dir / 'ParticipantModule' / 'Scripts'} && ./start_rpc.sh {port}"
        )
        error = stderr.read().decode()
        if error:
            raise Exception(
                f"Could not start RPC server on device {self.name}: {error}"
            )
        else:
            logger.info(f"Started RPC server on port {port} on device {self.name}.")

    def rpc_mm_test(self) -> bool:
        """
        Tests the RPC server by calling a basic torch.mm procedure and checking
        the results.
        """
        logger.info(f"Testing RPC server on device {self.name}.")
        connection = rpyc.connect(self.host, self.rpc_port)
        logger.info(f"Connected to RPC server on device {self.name}.")

        # Test a basic torch.mm call
        a = torch.tensor([[1, 2], [3, 4]])
        b = torch.tensor([[1, 2], [3, 4]])
        logger.info(f"Calling torch.mm on device {self.name}.")
        ret = connection.root.tensor_mm(a, b)
        logger.info(f"Received torch.mm result from device {self.name}.")

        return torch.all(torch.eq(ret, torch.mm(a, b)))

    def _expanduser_remote(self, path: pathlib.Path) -> pathlib.Path:
        """
        Small utility function that expands the "~" character in a path to
        match the remote user's home directory rather than the local user's.
        """
        expanded = pathlib.Path(str(path).replace("~", f"/home/{self.user}"))
        logger.debug(f"Device {self.name} expanded path {path} to {expanded}.")
        return expanded

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
        if not self.ssh_server_is_open():
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
        with self.ssh.open_sftp().file(true_path, "r") as file:
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
        if not self.ssh_server_is_open():
            raise DeviceUnavailableException(
                f"Device {self.name} is not available. "
                + f"Cannot create directory {remote_path}."
            )

        # Expand the remote path to match the remote user's home directory
        true_path = self._expanduser_remote(remote_path)

        # Create the directory, recursively creating parent dirs as needed
        sftp = self.ssh.open_sftp()
        logger.debug(f"sftp opened for device {self.name}.")
        parts = str(true_path).split("/")
        if parts[0] == "":
            parts = parts[1:]
            parts[0] = "/" + parts[0]
        logger.debug(f"Split path {true_path} into parts {parts}.")
        for i in range(len(parts)):
            current_path = "/".join(parts[: i + 1])
            try:
                logger.debug(f"Trying to listdir {current_path} on device {self.name}.")
                sftp.listdir(current_path)  # Test if path exists
            except (IOError, FileNotFoundError):  # Path does not exist
                logger.debug(
                    f"sftp listdir failed, trying to mkdir {current_path} on device {self.name}."
                )
                sftp.mkdir(current_path)
        sftp.close()
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
        if not self.ssh_server_is_open():
            raise DeviceUnavailableException(
                f"Device {self.name} is not available. "
                + f"Cannot check if path {remote_path} exists."
            )

        # Expand the remote path to match the remote user's home directory
        true_path = self._expanduser_remote(remote_path)

        # Check if the file or directory exists
        try:
            sftp = self.ssh.open_sftp()
            sftp.stat(str(true_path))
            return True
        except IOError:
            return False
        except Exception as e:
            logger.warning(
                f"Could not check if path {true_path} exists "
                + f"on device {self.name}: {e}"
            )
            raise e
        finally:
            sftp.close()

    def close_connections(self):
        """
        Close the ssh and sftp clients, if they are open.
        """
        try:
            self.ssh.close()
        except Exception as e:
            pass

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

    def ssh_server_is_open(self) -> bool:
        """
        Returns True if the specified client is available, False otherwise.

        Parameters:
        -----------
        client: str, default "ssh"
            The client to check. Must be either "ssh" or "sftp".
        """
        if not self.connected:
            return False
        try:
            self.ssh.exec_command("echo", timeout=1)
            return True
        except Exception as e:
            self.connected = False
            logger.info(f"Device {self.name} is not available: {e}")
            return False


class DeviceManager:
    """
    The DeviceManager class is responsible for managing the collection of
    known devices. It is responsible for maintaining the list of known devices
    and saving/loading them to/from a JSON file. It also maintains paramiko
    objects which control authentication and connection behavior.
    """

    # the path to the host machine's SSH config file
    ssh_config_dir: pathlib.Path = pathlib.Path("/host_ssh")

    # the path to the settings.yaml file
    settings_path: pathlib.Path = (
        utils.get_tracr_root() / "PersistentData" / "Configs" / "settings.yaml"
    )

    # ssh config objects for lookups
    ssh_config: paramiko.SSHConfig = paramiko.SSHConfig()

    # stores a list of Device objects
    devices: list = []

    def __init__(self):
        # parse the SSH config file
        with open(self.ssh_config_dir / "config", "r") as ssh_config_file:
            self.ssh_config.parse(ssh_config_file)

        # create a list of Device objects for all known devices
        self.load_known_devices()

    def load_known_devices(self):
        """
        Loads the known devices from the settings.yaml file. Idempotent.
        """

        def add_device(known_device_name, devices_list, ssh_config, input_lock):
            if ssh_config.lookup(known_device_name).get("hostname") is not None:
                logger.info(
                    f"Adding Device object for {known_device_name} to the list."
                )
                devices_list.append(
                    Device(
                        known_device_name,
                        ssh_config.lookup(known_device_name),
                        input_lock=input_lock,
                    )
                )
            else:
                raise ValueError(f"Device {known_device_name} is not a valid device.")

        threads = []
        password_lock = Lock()

        for known_device_name in self.get_known_device_names():
            # skip devices that are already in the list
            if self.get_devices_by(name=known_device_name):
                logger.debug(f"Device {known_device_name} is already in the list.")
                continue
            # create a thread to add the device to the list
            thread = Thread(
                target=add_device,
                args=(known_device_name, self.devices, self.ssh_config, password_lock),
            )
            threads.append(thread)
            thread.start()

        # wait for all threads to complete
        for thread in threads:
            thread.join()

    def deploy_rpc_services(self):
        """
        Uses RPyC's zero-deploy feature to deploy the RPyC services on all devices
        that are currently connectable.
        """
        available_devices = [
            dev.as_ssh_machine() for dev in self.get_devices_by(ssh_server_is_open=True)
        ]
        if not available_devices:
            logger.warning("No devices are currently available.")
            return
        logger.info(f"Deploying RPyC services to {len(available_devices)} devices.")

        dep = MultiServerDeployment(available_devices)
        dep2 = DeployedServer()

    def get_known_device_names(self) -> list:
        """
        Returns a list of the known devices saved in settings.yaml
        """
        with open(self.settings_path, "r") as settings_file:
            settings = oyaml.safe_load(settings_file)
        known_device_names = list(settings.get("Known_Devices", []))
        if not known_device_names:
            logger.warning(
                "No known devices found in settings.yaml. Use `tracr device add` to add a device."
            )
        return known_device_names

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
            raise ValueError(
                f"No user specified in lookup for {name}. "
                + f"Please check your ~/.ssh/config file to ensure {name} is listed."
            )

        # Add the device to the known devices list
        with open(self.settings_path, "r") as settings_file:
            settings = oyaml.safe_load(settings_file)
        if not settings.get("Known_Devices"):
            logger.info("Creating list of known devices in settings.yaml")
            settings["Known_Devices"] = []
        if name not in settings["Known_Devices"]:
            settings["Known_Devices"].append(name)
            with open(self.settings_path, "w") as settings_file:
                logger.info(f"Adding device {name} to settings.yaml")
                oyaml.safe_dump(settings, settings_file)

        # update the device list
        self.load_known_devices()

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

        dev_to_remove = matching_devs[0]
        self.devices.remove(dev_to_remove)

        with open(self.settings_path, "r") as settings_file:
            settings = oyaml.safe_load(settings_file)
        if name in settings["Known_Devices"]:
            settings["Known_Devices"].remove(dev_to_remove.name)
            with open(self.settings_path, "w") as settings_file:
                logger.info(f"Removing device {name} from settings.yaml")
                oyaml.safe_dump(settings, settings_file)
        else:
            logger.warning(
                f"Device {name} not found in settings.yaml. No device removed."
            )

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
