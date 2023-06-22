import socket
import pathlib
import paramiko
import ipaddress
import platform
import docker
import netifaces as ni
from getmac import get_mac_address

from exceptions import (
    MissingDeviceDataException,
    NoIPFoundException,
    NoMACFoundException,
)


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
        ip_address: str = "",
        ip_is_static: str = "",
        mac_address: str = "",
        hostname: str = "",
        ssh_username: str = "",
        nickname: str = "",
        description: str = "",
        os_family: str = "",
        cpu_arch: str = "",
        ram_MB: str = "",
    ):
        self.ip_address = ip_address
        self.ip_is_static = ip_is_static
        self.mac_address = mac_address
        self.hostname = hostname
        self.ssh_username = ssh_username
        self.nickname = nickname
        self.description = description
        self.os_family = os_family
        self.cpu_arch = cpu_arch
        self.ram_MB = ram_MB

    @classmethod
    def is_listening(cls, host, port=22, ttl=0.1):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(ttl)
        try:
            s.connect((str(host), port))
            return True
        except (socket.timeout, ConnectionRefusedError):
            return False
        finally:
            s.close()

    def get_ip_address(self, refresh=False):
        """Attempts to get the current IP address however possible"""
        if refresh or not self.ip_address:
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
            return self.ip_address

    def get_mac_address(self):
        """Uses getmac to attempt to find MAC, memoizes if successful"""
        if self.mac_address:
            return self.mac_address  # if already memoized
        if self.hostname:
            result = get_mac_address(hostname=self.hostname)
            if result:
                return result
        if self.ip_address:
            result = get_mac_address(ip=self.ip_address)
            if result:
                return result
        raise NoMACFoundException(f"Hostname: {self.hostname}, IP: {self.ip_address}")

    def get_hostname(self, silent=False):
        """Uses socket to attempt to find hostname, memoizes if successful"""
        if self.hostname:
            return self.hostname  # if already memoized
        try:
            return socket.gethostbyaddr(self.ip_address)[0]
        except Exception as e:
            if not silent:
                print(f"No hostname found for {self.ip_address} : {e}")
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
            s.connect((self.get_ip_address(), port))
        except (socket.timeout, ConnectionRefusedError):
            return False
        finally:
            s.close()
            return True

    def set_username(self, username):
        """Sets the username for SSH connections"""
        self.username = username

    def set_os_family(self, os_family):
        """Sets the os family"""
        self.os_family = os_family

    def set_cpu_architecture(self, cpu_architecture):
        """Sets the cpu_architecture attribute"""
        self.cpu_architecture = cpu_architecture

    def set_ram_MB(self, ram_MB):
        """Sets the ram_MB attribute"""
        self.ram_MB = ram_MB

    def set_local_hostname(self, local_hostname):
        """Sets the local_hostname attribute"""
        self.local_hostname = local_hostname

    def get_username(self):
        """Returns the preferred username for SSH connections"""
        return self.username

    def retrieve_system_info(self, keyfile_path, save_results=True, pw=None):
        """Connects via SSH to get system info."""
        # Make sure keyfile_path is a Path object
        assert isinstance(
            keyfile_path, pathlib.Path
        ), "keyfile_path must be a pathlib.Path object"

        # Get system password from user
        if not pw:
            pw = input("\nPlease enter local system password: ")

        # Create a new SSH client
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        # Load the private key
        private_key = paramiko.RSAKey.from_private_key_file(
            str(keyfile_path), password=pw
        )

        # Connect to the server using the private key
        client.connect(
            self.get_ip_address(), username=self.get_username(), pkey=private_key
        )

        # Dict to store the information
        info = {}

        # List of commands to execute
        commands = {
            "os_family": "uname -s",
            "cpu_architecture": "uname -m",
            "ram": "free -m | awk 'NR==2{printf $2}'",  # Returns in MB
            "hostname": "hostname",
        }

        # Execute each command
        for key, command in commands.items():
            stdin, stdout, stderr = client.exec_command(command)
            info[key] = stdout.read().decode().strip()

        # Close the connection
        client.close()

        # Return (after saving args, if necessary)
        if save_results:
            self.set_os_family(info["os_family"])
            self.set_cpu_architecture(info["cpu_architecture"])
            self.set_ram_MB(info["ram"])
            self.set_local_hostname(info["hostname"])
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
            if is_listening(host, port=port, ttl=ttl):
                responsive_hosts.append(host)

        self.devices = [Device(session_ip=str(host)) for host in responsive_hosts]
        return

    def display_devices(self):
        """
        Display the IP addresses and hostnames of all the devices in the LAN.
        """
        for i, device in enumerate(self.devices):
            ip = device.get_ip_address()
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
