import socket
import uuid
import time
import re
import pathlib
import paramiko
import ipaddress
import json
import platform
import docker
import netifaces as ni
from getmac import get_mac_address
from pathlib import Path

import api.config_mgr as config_mgr
from api.exceptions import (
    MissingDeviceDataException,
    NoIPFoundException,
    NoMACFoundException,
    SSHNotReadyException,
    NoDeviceConfigException,
)


# Global constants

DEB_CMD_OSFAMILY = "uname -s"
DEB_CMD_CPUARCH = "uname -m"
DEB_CMD_RAMMB = "free -m | awk 'NR==2{printf $2}'"  # Returns in MB
DEB_CMD_HOSTNAME = "hostname"

PROJECT_ROOT = Path(__file__).parent.parent.absolute()
DEFAULT_CONTROLLER_CONFIG_FP = PROJECT_ROOT / "setup/default_controller_config.json"
with open(DEFAULT_CONTROLLER_CONFIG_FP, "r") as f:
    config_file_contents = json.load(f)
DEFAULT_KNOWN_DEVICE_DICT = config_file_contents["known_devices"][0]
DEFAULT_DEVICE_CONFIG_FP = PROJECT_ROOT / "setup/default_device_config.json"
with open(DEFAULT_DEVICE_CONFIG_FP, "r") as f:
    config_file_contents = json.load(f)
DEFAULT_REMOTE_DEVICE_DICT = config_file_contents


# Global utility functions


def mac_doublecheck(host, repeat, wait):
    """
    mac_doublecheck
        Sends multiple UDP packets to boost the success rate of get_mac_address() function.
    Parameters:
    -----------
    host: str
        The IP address or hostname of the target device.
    repeat: int
        The number of times to send a UDP packet to the target device.
    wait: float
        The number of seconds to wait between sending UDP packets.
    Returns:
    --------
    str or None
        The MAC address of the target device if found, None otherwise.
    """
    # check if host matches IP address pattern
    is_ip = re.match(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$", host)

    macs = []
    for i in range(repeat):
        if is_ip:
            macs.append(get_mac_address(ip=host))
        else:
            macs.append(get_mac_address(hostname=host))
        time.sleep(wait)
    macs = list(set(macs))
    for m in macs:
        if bool(m) and not m == "00:00:00:00:00:00":
            return m
    return None


def convert_tenacity(tenacity: int) -> tuple:
    """
    Convenience function to translate 'tenacity' into actual parameters.
    It's a bit arbitrary, but it keeps things concise.

    Parameters:
    -----------
    tenacity: int
        A number 1-5 representing how much effort should be spent in finding
        network info (e.g., searching for mac address)

    Returns:
    --------
    params: tuple[int, float, int]
        A tuple containing the ordered parameters 'repeats', 'wait_time', and
        'recurse'
    """
    tenacity = int(tenacity)
    if tenacity < 1:
        tenacity = 1
    elif tenacity > 5:
        tenacity = 5
    repeats = tenacity
    wait_time = 0.01 * 2**tenacity
    recurse = sum(((tenacity > 1), (tenacity > 4)))

    return repeats, wait_time, recurse


class Controller:
    """
    A class that represents the controller device (user's machine).
    """

    def __init__(self):
        self.config = config_mgr.ControllerConfigs()


class Device:

    """
    A class that represents a device on the LAN.

    Attributes
    ----------
    ip_address (string) : the local IP address of the device
    mac_address (string) : the MAC address of the device
    hostname (string) : the hostname of the device
    username (string) : the username that should be used to SSH in
    nickname (string) : a name the user can save for this device in the testbed
    description (string) : a brief description of the device

    Methods
    -------
    get_ip_address : gets ip
    get_mac_address : gets MAC
    get_hostname : gets hostname

    Subclasses
    ----------
    Controller : represent's the controller device (user's machine)
    """

    def __init__(self, controller, **kwargs):
        """
        Initializes a Device object from a given device information.

        Parameters
        ----------
        controller : Controller
            The controller object that this device is associated with
        last_ip : str, optional
            The last known IP address of the device, by default ""
        static_ip : str, optional
            The static IP address of the device, by default ""
        network_interfaces : list-of-dict, optional
            A list of network interfaces on the device, by default []. Each
            interface is a dict with keys 'name', 'mac', and 'type'.
        current_mac : str, optional
            The current MAC address of the device, by default ""
        hostname : str, optional
            The hostname of the device, by default ""
        ssh_username : str, optional
            The username to use when SSHing into the device, by default ""
        ssh_pw : str, optional
            The password to use when SSHing into the device
        ssh_pubkey_fp: str, optional
            The path to the local SSH public key for this device
        ssh_privkey_fp: str, optional
            The path to the local SSH private key for this device
        device_nickname : str, optional
            A nickname for the device, by default ""
        description : str, optional
            A description of the device, by default ""
        os_family : str, optional
            The operating system family of the device, by default ""
        cpu_architecture : str, optional
            The CPU architecture of the device, by default ""
        ram_MB : str, optional
            The amount of RAM on the device, in MB, by default ""
        base_image : str, optional
            The base_image of device, by default ""
        auto_update : bool, optional
            Whether to automatically update the device's information during init, by default False
        """
        default_kwargs = {
            "last_ip": "",
            "static_ip": "",
            "network_interfaces": [],
            "current_mac": "",
            "hostname": "",
            "ssh_username": "",
            "ssh_pw": "",
            "ssh_pubkey_fp": "",
            "ssh_privkey_fp": "",
            "device_nickname": "",
            "description": "",
            "os_family": "",
            "cpu_architecture": "",
            "ram_MB": "",
            "base_image": "",
            "auto_update": False,
        }
        default_kwargs.update(kwargs)
        auto_update = default_kwargs.pop("auto_update")
        for key, value in default_kwargs.items():
            self._set(key, value)

        self.config = config_mgr.DeviceConfigs()
        self.controller = controller

        if auto_update:
            self.infer_missing()

    def __eq__(self, other):
        if isinstance(other, Device):
            return self.uuid == other.uuid
        return False

    def __hash__(self):
        return hash(self.uuid)

    @classmethod
    def create_from_dict(cls, device_info: dict, auto_update=False):
        device_instance = Device(**device_info, auto_update=auto_update)
        return device_instance

    @classmethod
    def get_default_attribs(cls):
        return DEFAULT_KNOWN_DEVICE_DICT.keys()

    @classmethod
    def is_listening(cls, host, port=22, ttl=0.1):
        """
        Checks if a socket is listening on the given host and port.

        Parameters:
        -----------
        host: str
            The IP address or hostname of the target machine.
        port: int, optional
            The port number to check, by default 22.
        ttl: float, optional
            The maximum time to wait for a response, in seconds, by default 0.1.

        Returns:
        --------
        bool
            True if a socket is listening on the given host and port, False otherwise.
        """
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(ttl)
        try:
            s.connect((str(host), port))
            return True
        except (socket.timeout, ConnectionRefusedError):
            return False
        finally:
            s.close()

    @classmethod
    def is_ready(cls, device):
        """
        Checks if a device is ready to accept an experiment.

        Parameters:
        -----------
        device: Device
            The target device.

        Returns:
        --------
        bool
            True if the device is ready, False otherwise.
        """
        # TODO: implement this
        return False

    @classmethod
    def get_ip_from_mac(cls, mac, cidr_block="192.168.1.0/24", repeat=3, wait=0.01):
        """
        Gets the IP address of a device with the given MAC address.

        Parameters:
        -----------
        cls: class
            The class object.
        mac: str
            The MAC address of the target device.
        cidr_block: str, optional
            The CIDR block to scan for the target device's IP address, by default "192.168.1.0/24".
        repeat: int, optional
            The number of times to send a UDP packet to the target device, by default 3.
        wait: float, optional
            The number of seconds to wait between sending UDP packets, by default 0.01.

        Raises:
        -------
        NoIPFoundException
            If the IP address of the device with the given MAC address cannot be found.

        Returns:
        --------
        str
            The IP address of the device with the given MAC address.
        """
        possible_ips = [str(ip) for ip in ipaddress.ip_network(cidr_block).hosts()]

        ip_mac_pairs = [(ip, mac_doublecheck(ip, repeat, wait)) for ip in possible_ips]
        for ip, m in ip_mac_pairs:
            if m == mac:
                return ip

        raise NoIPFoundException(f"MAC Address = {mac}")

    @classmethod
    def fetch_data(
        cls,
        last_ip=None,
        mac_address=None,
        hostname=None,
        repeat=3,
        wait=0.01,
        recurse=1,
    ) -> dict:
        """Fetches data from an unknown device, given any one of its identifiers"""

        data = {"last_ip": last_ip, "current_mac": mac_address, "hostname": hostname}

        if not data.get("last_ip"):
            if data.get("hostname"):
                try:
                    data["last_ip"] = socket.gethostbyname(data["hostname"])
                except socket.gaierror:
                    pass
            if data.get("current_mac") and not data.get("last_ip"):
                try:
                    data["last_ip"] = cls.get_ip_from_mac(data["current_mac"])
                except NoIPFoundException:
                    pass
        if not data.get("current_mac"):
            if data.get("hostname"):
                data["current_mac"] = mac_doublecheck(
                    data["hostname"], repeat=repeat, wait=wait
                )
            if data.get("last_ip") and not data.get("current_mac"):
                data["current_mac"] = mac_doublecheck(
                    data["last_ip"], repeat=repeat, wait=wait
                )
        if not data.get("hostname"):
            if data.get("last_ip"):
                try:
                    data["hostname"] = socket.gethostbyaddr(data["last_ip"])[0]
                except socket.herror:
                    pass

        if recurse > 0 and not all(data.values()):
            return cls.fetch_data(**data, recurse=recurse - 1)
        else:
            for value in data.values():
                if not value:
                    value = ""
            return data

    def _set(self, attribute, value, force=False):
        """Sets an attribute of the device with validation. Class use only."""
        if not attribute in set(DEFAULT_KNOWN_DEVICE_DICT.keys()):
            raise AttributeError(f"Device has no attribute '{attribute}'")
        if attribute == "uuid":
            if self.uuid and not force:
                raise AttributeError("Device already has a UUID")
            if not isinstance(value, uuid.UUID):
                raise TypeError("UUID must be a UUID object")
            self.uuid = value
        elif attribute == "network_interfaces":
            if not isinstance(value, list):
                raise TypeError("Network interfaces must be a list")
            for interface in value:
                if not isinstance(interface, dict):
                    raise TypeError("Network interfaces must be a list of dicts")
                if not set(
                    DEFAULT_KNOWN_DEVICE_DICT["network_interfaces"][0].keys()
                ) == set(interface.keys()):
                    raise TypeError(
                        "Network interfaces must be a list of dicts with keys: "
                        + ", ".join(
                            DEFAULT_KNOWN_DEVICE_DICT["network_interfaces"][0].keys()
                        )
                    )
            self.network_interfaces = value
        elif attribute == "current_mac":
            if not isinstance(value, str):
                raise TypeError("Current MAC address must be a string")
            if (
                not re.match(r"([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})", value)
                and not value == ""
            ):
                raise ValueError("Current MAC address must be a valid MAC address")
            if value == "00:00:00:00:00:00":
                raise ValueError("Current MAC address cannot be all zeros")
            known_macs = [
                interface.get("mac")
                for interface in self.network_interfaces
                if interface.get("mac")
            ]
            if value not in known_macs:
                self.network_interfaces.append({"mac": value, "name": "", "type": ""})
            self.current_mac = value
        elif attribute == "ssh_username":
            if not isinstance(value, str):
                raise TypeError("SSH username must be a string")
            self.ssh_username = value
        elif attribute == "ssh_pw":
            if not isinstance(value, str):
                raise TypeError("SSH password must be a string")
            self.ssh_pw = value
        elif attribute == "ssh_pubkey_fp":
            if not isinstance(value, Path):
                try:
                    value = Path(value)
                except TypeError:
                    raise TypeError(
                        "SSH public key fingerprint must be a string or Path"
                    )
            value = value.expanduser().absolute()
            if not value.exists():
                raise FileNotFoundError(
                    "SSH public key fingerprint file does not exist"
                )
            self.ssh_pubkey_fp = value
        elif attribute == "ssh_privkey":
            if not isinstance(value, Path):
                try:
                    value = Path(value)
                except TypeError:
                    raise TypeError("SSH private key must be a string or Path")
            value = value.expanduser().absolute()
            if not value.exists():
                raise FileNotFoundError("SSH private key file does not exist")
            self.ssh_privkey = value
        elif attribute == "device_nickname":
            if not isinstance(value, str):
                raise TypeError("Device nickname must be a string")
            self.device_nickname = value
        elif attribute == "description":
            if not isinstance(value, str):
                raise TypeError("Description must be a string")
            self.description = value
        elif attribute == "hostname":
            if not isinstance(value, str):
                raise TypeError("Hostname must be a string")
            self.hostname = value
        elif attribute == "last_ip":
            if not isinstance(value, str):
                raise TypeError("Last IP must be a string")
            if (
                not re.match(r"^(?:[0-9]{1,3}\.){3}[0-9]{1,3}$", value)
                and not value == ""
            ):
                raise ValueError("Last IP must be a valid IPv4 address")
            self.last_ip = value
        elif attribute == "static_ip":
            if not isinstance(value, str):
                raise TypeError("Static IP must be a string")
            if (
                not re.match(r"^(?:[0-9]{1,3}\.){3}[0-9]{1,3}$", value)
                and not value == ""
            ):
                raise ValueError("Static IP must be a valid IPv4 address")
            self.static_ip = value
        elif attribute == "base_image":
            if not isinstance(value, str):
                raise TypeError("Base image must be a string")
            self.base_image = value
        elif attribute == "os_family":
            if not isinstance(value, str):
                raise TypeError("OS family must be a string")
            self.os_family = value
        elif attribute == "ram_MB":
            if not (isinstance(value, int) or isinstance(value, str)):
                raise TypeError("RAM must be an integer or string")
            if isinstance(value, int):
                value = str(value)
            self.ram_MB = value
        elif attribute == "cpu_architecture":
            if not isinstance(value, str):
                raise TypeError("CPU architecture must be a string")
            self.cpu_architecture = value

    def _get(self, attribute, as_str=True):
        """Simple getter for device attributes. Class use only."""
        result = getattr(self, attribute)
        if as_str:
            result = str(result)
        return result

    def assign_new_uuid(self, force=False):
        """Assigns a new UUID to the device."""
        self._set("uuid", uuid.uuid4(), force=force)

    def refresh(self, include_system_info=False):
        """Refreshes the device's information."""
        try:
            self._set("last_ip", self.get_current_ip(refresh=True))
        except (NoIPFoundException, MissingDeviceDataException):
            pass
        new_hn = self.get_hostname(refresh=True)
        if new_hn:
            self._set("hostname", new_hn)
        try:
            self._set("current_mac", self.get_current_mac(refresh=True))
        except (NoMACFoundException, MissingDeviceDataException):
            pass

        if include_system_info:
            self.infer_missing()

    def get_shortname(self):
        """Searches attributes to find a shortname for the device."""
        if self.device_nickname:
            return self.device_nickname
        elif self.hostname:
            return self.hostname.split(".")[0]
        elif self.last_ip:
            return self.last_ip
        elif self.current_mac:
            return self.current_mac
        else:
            return "Device"

    def infer_missing(self, defaults=DEFAULT_KNOWN_DEVICE_DICT):
        """
        Attempts to infer missing device information using whatever information
        is available.

        Parameters:
        -----------
        defaults: dict, optional
            A dictionary of default values to use if no information can be inferred,
            by default uses DEFAULT_DEVICE_DICT constant, but can also be set to use
            the values in the device's config file.
        """
        # find IP, hostname, and MAC first
        ipmachost = Device().fetch_data(
            last_ip=self.last_ip, hostname=self.hostname, mac_address=self.current_mac
        )
        for key, value in ipmachost.items():
            self._set(key, value)

        # ideally, we have a uuid to identify the device
        if self.uuid and self.uuid in self.controller.config.get_known_uuids():
            for device in self.controller.config.get_known_devices():
                if uuid.UUID(device["uuid"]) == self.uuid:
                    for key, value in device.items():
                        self._set(key, value, force=True)
        # alternatively, the MAC is almost as good
        elif (
            self.current_mac
            and self.current_mac in self.controller.config.get_known_macs()
        ):
            for device in self.controller.config.get_known_devices():
                if self.current_mac in [
                    ni["mac"] for ni in device["network_interfaces"]
                ]:
                    for key, value in device.items():
                        self._set(key, value, force=True)

    def as_dict(self, for_controller=True):
        """
        Returns a dictionary representation of the device.
        """
        included_attrs = (
            set(DEFAULT_KNOWN_DEVICE_DICT.keys())
            if for_controller
            else (DEFAULT_REMOTE_DEVICE_DICT.keys())
        )

        def gets_saved(attr_name):
            return (
                not attr_name.startswith("__")
                and not callable(getattr(self, attr_name))
                and attr_name in DEFAULT_KNOWN_DEVICE_DICT.keys()
                and getattr(self, attr_name, False)
            )

        relevant_attrs = {
            attr: getattr(self, attr) for attr in dir(self) if gets_saved(attr)
        }

        result = DEFAULT_KNOWN_DEVICE_DICT.copy()
        result.update(relevant_attrs)
        return result

    def absorb(self, other):
        """
        Absorbs the attributes of another device into this one.
        """
        if not isinstance(other, Device):
            raise TypeError("Can only absorb attributes of another Device object")
        if self.uuid != other.uuid:
            raise ValueError(
                "Can only absorb attributes of a device with the same UUID"
            )
        for attr in dir(other):
            if (
                not attr.startswith("__")
                and not callable(getattr(other, attr))
                and attr in DEFAULT_KNOWN_DEVICE_DICT.keys()
            ):
                if getattr(self, attr, "fail") == "fail":
                    continue
                elif not getattr(self, attr):
                    self._set(getattr(other, attr))

    def open_ssh_client(self, debug=False):
        """
        Returns a paramiko SSHClient instance that is connected to the device.
        """
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        rsa_key = paramiko.RSAKey(filename=self.ssh_privkey_fp)
        try:
            client.connect(
                self.last_ip,
                username=self.ssh_username,
                pkey=rsa_key,
            )
        except Exception as e:
            if debug:
                print(e)
            return None
        return client

    def ready_for_SSH(self, debug=False):
        """
        Returns True if the device is not only listening on port 22, but
        also accepting connections using the parameters saved as attributes.

        Parameters:
        -----------
        debug: bool, optional
            If True, print any exceptions that occur during the SSH connection
        """
        # immediately return False if we don't have enough information
        if not all(
            (
                (self.last_ip or self.hostname or self.static_ip),
                self.ssh_username,
                self.ssh_privkey_fp,
            )
        ):
            return False

        # check if the device is listening on port 22
        if not self.is_responsive():
            return False

        # finally, check if we can connect using the stored credentials
        try:
            with self.open_ssh_client() as client:
                client.exec_command("echo 'hello world'")
        except Exception as e:
            if debug:
                print(e)
            return False
        return True

    def get_current_ip(self, refresh=False):
        """Attempts to get the current IP address however possible"""
        if refresh or not self.last_ip:
            if self.hostname:
                try:
                    return socket.gethostbyname(self.hostname)
                except socket.gaierror:
                    pass
            if self.current_mac:
                neighbors = LAN.get_responsive_hosts()
                for ip in neighbors:
                    if mac_doublecheck(ip, 5, 0.1) == self.current_mac:
                        return ip
                search_param = f"MAC Address = {self.current_mac}"
                raise NoIPFoundException(search_param)
            else:
                raise MissingDeviceDataException("hostname or mac_addr", "IP Address")
        else:
            return self.last_ip

    def get_current_mac(self, refresh=False, tenacity=3):
        """Uses getmac to attempt to find MAC, memoizes if successful"""
        if self.current_mac and not refresh:
            return self.current_mac  # if already memoized
        repeats, wait_time, recurse = convert_tenacity(tenacity)
        if self.hostname:
            result = mac_doublecheck(self.hostname, repeats, wait_time)
            if result:
                return result
        if self.last_ip:
            result = mac_doublecheck(self.last_ip, repeats, wait_time)
            if result:
                return result
        raise NoMACFoundException(f"Hostname: {self.hostname}, IP: {self.last_ip}")

    def get_hostname(self, silent=True, refresh=False):
        """Uses socket to attempt to find hostname, memoizes if successful"""
        if self.hostname and not refresh:
            return self.hostname  # if already memoized
        try:
            return socket.gethostbyaddr(self.last_ip)[0]
        except socket.herror as e:
            if not silent:
                print(f"No hostname found for {self.last_ip} : {e}")
            return None

    def set_up_passwordless_ssh(self):
        """Sets up passwordless ssh on the device"""
        # TODO: implement
        pass

    def is_responsive(self, ttl=0.1, port=22):
        """Checks if host is listening on specified port (22 by default)"""
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(ttl)
        try:
            s.connect((self.get_current_ip(), port))
        except (socket.timeout, ConnectionRefusedError):
            return False
        finally:
            s.close()
            return True

    def get_username(self):
        """Returns the preferred username for SSH connections"""
        return self.username

    def fetch_remote_config(self) -> dict:
        """Uses DeviceConfigs to fetch the contents of the remote config."""
        if not self.ready_for_SSH():
            raise SSHNotReadyException("fetch_remote_config", self.get_current_ip())
        with self.open_ssh_client() as client:
            return self.config.get_stored_device_configs(client)

    def ask_system_info(self, store_results: bool = False) -> dict:
        """
        Connects via SSH to get system info from the device by running
        commands on the device.

        Parameters:
        -----------
        store_results: bool, optional
            If True, store the results in the appropriate attributes

        Returns:
        --------
        info: dict
            A dictionary containing the system information
        """
        if not self.ready_for_SSH():
            raise SSHNotReadyException("ask_system_info", self.get_current_ip())

        # Dict to store the information
        info = {}

        # List of commands to execute
        commands = {
            "os_family": DEB_CMD_OSFAMILY,
            "cpu_architecture": DEB_CMD_CPUARCH,
            "ram_MB": DEB_CMD_RAMMB,
            "hostname": DEB_CMD_HOSTNAME,
        }

        with self.open_ssh_client() as client:
            # Execute each command
            for key, command in commands.items():
                stdin, stdout, stderr = client.exec_command(command)
                info[key] = stdout.read().decode().strip()

        # Return (after saving args, if necessary)
        if store_results:
            self.set_os_family(info["os_family"])
            self.set_cpu_architecture(info["cpu_architecture"])
            self.set_ram_MB(info["ram_MB"])
            self.set_hostname(info["hostname"])

        return info

    def ready_to_deploy(self):
        """Returns True if the device is ready to be deployed to"""
        is_listening = self.is_responsive()

        # TODO:
        # Check for repo matching the controller device
        # Check for ability to ssh
        # Check for device info in config files
        # Check for working base image
        # Check for connectivity to other devices


class LAN:

    """
    A class that represents the local network, specifically with respect to
    connectable IoT device setup and discovery.

    Attributes
    ----------
    devices : list
        a list of Device objects that have been discovered on the LAN

    Methods
    -------
    discover_devices(ip_range):
        Discovers devices on the LAN and adds them to the devices list.
    """

    def __init__(self, controller=None):
        """Constructs all the necessary attributes for the LAN object."""
        self.devices = []
        if controller:
            self.controller = controller
        else:
            self.controller = Controller()

    @classmethod
    def get_responsive_hosts(cls, cidr_block="192.168.1.0/24", port=22, ttl=0.1):
        """Searches the local network for hosts that respond to socket connections
        on the specified port"""
        ips = ipaddress.ip_network(cidr_block).hosts()
        return [str(ip) for ip in ips if Device.is_listening(ip, port=port, ttl=ttl)]

    @classmethod
    def find_all_devices(cls, cidr_block="192.168.1.0/24", tenacity=3):
        """
        Searches the local network for all devices, even if they are not open to
        socket connections.

        Parameters:
        -----------
        cidr_block (str) : The range of IPs to scan in CIDR format
        tenacity (int) : An arbitrary rating of 1 to 5 for how much time should
            be spent trying to find devices. 1 is the lowest. (default: 3)

        Returns:
        --------
        device_list (list[dict]) : A list of dictionaries containing the ip, mac,
            and hostname of each device found
        """
        # translate tenacity to actual parameters
        repeats, wait_time, recurse = convert_tenacity(tenacity)

        ips = [str(ip) for ip in ipaddress.ip_network(cidr_block).hosts()]
        ip_mac_tuples = [
            (ip, mac_doublecheck(ip, repeat=repeats, wait=wait_time)) for ip in ips
        ]
        ip_mac_tuples = [tup for tup in ip_mac_tuples if tup[1]]
        found_devs = [
            Device().fetch_data(
                ip=ip, mac=mac, repeat=repeats, wait=wait_time, recurse=recurse
            )
            for ip, mac in ip_mac_tuples
        ]
        return found_devs

    def discover_devices(self, cidr_block, port=22, ttl=0.1):
        """
        Discover devices on the LAN within the given IP range by attempting to
        establish a socket connection (on port 22 by default).

        TODO: This should really use threading.

        Parameters:
        -----------
        cidr_block (str) : The range of IPs to scan in CIDR format
            (e.g., "192.168.1.0/24").
        ttl (float) : Time To Live; how long to wait for a socket connection
            before moving on
        port (int) : Which port to attempt socket connections through
        """
        ip_range = ipaddress.ip_network(cidr_block).hosts()
        responsive_hosts = []

        for host in ip_range:
            if Device().is_listening(host, port=port, ttl=ttl):
                responsive_hosts.append(host)

        self.devices = [Device(session_ip=str(host)) for host in responsive_hosts]
        return

    def display_devices(self):
        """
        Display the IP addresses and hostnames of all the devices in the LAN.
        """
        for i, device in enumerate(self.devices):
            ip = device.get_current_ip()
            hname = device.get_hostname(silent=True)
            if not hname:
                hname = "No DNS record found."
            mac = device.get_current_mac()
            print(
                f"\nDEVICE {i+1}",
                "---------",
                f"\tIP Address: {ip}",
                f"\tHostname: {hname}",
                f"\tMAC Address: {mac}",
                sep="\n",
            )
        print("")
