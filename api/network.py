import socket
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
DEFAULT_DEVICE_DICT = config_file_contents["known_devices"][0]


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

    def __init__(
        self,
        last_ip: str = "",
        static_ip: str = "",
        mac_address: str = "",
        hostname: str = "",
        ssh_username: str = "",
        ssh_pw: str = "",
        ssh_pubkey_fp: str = "",
        ssh_privkey_fp: str = "",
        device_nickname: str = "",
        description: str = "",
        os_family: str = "",
        cpu_architecture: str = "",
        ram_MB: str = "",
        base_image: str = "",
        auto_update: bool = False,
    ):
        """
        Initializes a Device object from a given device information.

        Parameters
        ----------
        last_ip : str, optional
            The last known IP address of the device, by default ""
        static_ip : str, optional
            The static IP address of the device, by default ""
        mac_address : str, optional
            The MAC address of the device, by default ""
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
        self.last_ip = last_ip
        self.static_ip = static_ip
        self.mac_address = mac_address
        self.hostname = hostname
        self.ssh_username = ssh_username
        self.ssh_pw = ssh_pw
        self.ssh_pubkey_fp = Path(ssh_pubkey_fp).expanduser()
        self.ssh_privkey_fp = Path(ssh_privkey_fp).expanduser()
        self.device_nickname = device_nickname
        self.description = description
        self.os_family = os_family
        self.cpu_architecture = cpu_architecture
        self.ram_MB = ram_MB
        self.base_image = base_image

        if auto_update:
            self.refresh(include_system_info=True)

    @classmethod
    def create_from_dict(cls, device_info: dict, auto_update=False):
        device_instance = Device(**device_info, auto_update=auto_update)
        return device_instance

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

        data = {"last_ip": last_ip, "mac_address": mac_address, "hostname": hostname}

        if not data.get("last_ip"):
            if data.get("hostname"):
                try:
                    data["last_ip"] = socket.gethostbyname(data["hostname"])
                except socket.gaierror:
                    pass
            if data.get("mac_address") and not data.get("last_ip"):
                try:
                    data["last_ip"] = cls.get_ip_from_mac(data["mac_address"])
                except NoIPFoundException:
                    pass
        if not data.get("mac_address"):
            if data.get("hostname"):
                data["mac_address"] = mac_doublecheck(
                    data["hostname"], repeat=repeat, wait=wait
                )
            if data.get("last_ip") and not data.get("mac_address"):
                data["mac_address"] = mac_doublecheck(
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
            return data

    def refresh(self, include_system_info=False):
        """Refreshes the device's information."""
        try:
            self.last_ip = self.get_current_ip(refresh=True)
        except (NoIPFoundException, MissingDeviceDataException):
            pass
        new_hn = self.get_hostname(refresh=True)
        if new_hn:
            self.hostname = new_hn
        try:
            self.mac_address = self.get_mac_address(refresh=True)
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
        elif self.mac_address:
            return self.mac_address
        else:
            return "Device"

    def infer_missing(self, defaults=DEFAULT_DEVICE_DICT):
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
        if not self.last_ip:
            try:
                self.get_current_ip(refresh=True)
            except (NoIPFoundException, MissingDeviceDataException):
                if self.static_ip:
                    self.last_ip = self.static_ip
        if self.last_ip and not self.hostname:
            self.hostname = self.get_hostname(silent=True, refresh=True)
        if self.last_ip or self.hostname:
            try:
                self.mac_address = self.get_mac_address(refresh=True)
            except NoMACFoundException:
                pass

        # if we can establish an SSH connection to the device, we can get
        # more information
        if self.ready_for_SSH():
            self.ask_system_info(store_results=True)

        # finally, fill in any missing values with defaults
        for key, value in defaults.items():
            instance_attribute = getattr(self, key, "nonexistent")
            if instance_attribute == "nonexistent":
                pass
            elif not instance_attribute:
                setattr(self, key, value)

    def as_dict(self):
        """
        Returns a dictionary representation of the device.
        """

        def gets_saved(attr_name):
            return (
                not attr_name.startswith("__")
                and not callable(getattr(self, attr_name))
                and attr_name in DEFAULT_DEVICE_DICT.keys()
                and getattr(self, attr_name, False)
            )

        relevant_attrs = {
            attr: getattr(self, attr) for attr in dir(self) if gets_saved(attr)
        }

        result = DEFAULT_DEVICE_DICT.copy()
        result.update(relevant_attrs)
        return result

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
            if self.mac_address:
                neighbors = LAN.get_responsive_hosts()
                for ip in neighbors:
                    if get_mac_address(ip=ip) == self.mac_address:
                        return ip
                search_param = f"MAC Address = {self.mac_address}"
                raise NoIPFoundException(search_param)
            else:
                raise MissingDeviceDataException("hostname or mac_addr", "IP Address")
        else:
            return self.last_ip

    def get_mac_address(self, refresh=False, tenacity=3):
        """Uses getmac to attempt to find MAC, memoizes if successful"""
        if self.mac_address and not refresh:
            return self.mac_address  # if already memoized
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

    def set_username(self, username):
        """Sets the username for SSH connections"""
        if not username or not isinstance(username, str):
            return
        self.username = username

    def set_os_family(self, os_family):
        """Sets the os family"""
        if not os_family or not isinstance(os_family, str):
            return
        self.os_family = os_family

    def set_cpu_architecture(self, cpu_architecture):
        """Sets the cpu_architecture attribute"""
        if not cpu_architecture or not isinstance(cpu_architecture, str):
            return
        self.cpu_architecture = cpu_architecture

    def set_ram_MB(self, ram_MB):
        """Sets the ram_MB attribute"""
        if not ram_MB:
            return
        if isinstance(ram_MB, str):
            try:
                ram_MB = int(ram_MB)
            except ValueError:
                return
        self.ram_MB = ram_MB

    def set_hostname(self, hostname):
        """Sets the local_hostname attribute"""
        if not hostname or not isinstance(hostname, str):
            return
        self.hostname = hostname

    def get_username(self):
        """Returns the preferred username for SSH connections"""
        return self.username

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


class Controller(Device):

    """
    A child class of Device that represents the controller device, which is
    usually the machine the user is on.

    Attributes
    ----------
    static_ip (string) : the local IP address of the device
    mac_address (string) : the MAC address of the device
    hostname (string) : the hostname of the device

    Methods
    -------
    get_mac_address : gets MAC
    get_hostname : gets hostname
    """

    def __init__(self, net_interface=None):
        system_info = platform.uname()
        self.os_family = system_info.system
        self.release = system_info.release
        self.architecture = system_info.machine

        self.net_interface = net_interface
        if not self.net_interface:
            interface_list = ni.interfaces()
            self.net_interface = interface_list[0]

        self.hostname = socket.gethostname()
        self.ip_address = ni.ifaddresses(self.net_interface)[ni.AF_INET][0]["addr"]
        self.mac_address = get_mac_address(interface=self.net_interface)


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
            mac = device.get_mac_address()
            print(
                f"\nDEVICE {i+1}",
                "---------",
                f"\tIP Address: {ip}",
                f"\tHostname: {hname}",
                f"\tMAC Address: {mac}",
                sep="\n",
            )
        print("")
