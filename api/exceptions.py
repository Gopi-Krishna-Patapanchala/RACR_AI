class InvalidConfigFileException(Exception):
    """
    An exception raised when a config file is invalid.
    """

    def __init__(self, fp, message="Cannot load from invalid config file: "):
        self.message = message + fp
        super().__init__(self.message)


class DeviceUnavailableException(Exception):
    """
    Raised if a network operation is attempted on a device that is not available.
    """

    def __init__(self, message):
        super().__init__(message)


class DeviceNotSetupException(Exception):
    """
    Raised if a device is initialized without being setup.
    """

    def __init__(self, message):
        super().__init__(message)


class DeviceNameConflictException(Exception):
    """
    Raised if two devices are found with the same name.
    """

    def __init__(self, message):
        super().__init__(message)


class ExperimentNameConflictException(Exception):
    """
    Raised if a user attempts to make two experiments with the same name.
    """

    def __init__(self, message):
        super().__init__(message)


class MalformedUUIDException(Exception):
    """
    Raised if a value expected to be a valid UUID is not.
    """

    def __init__(self, message):
        super().__init__(message)


class UUIDExistsException(Exception):
    """
    Raised if an operation attempts to overwrite an existing UUID.
    """

    def __init__(self, message):
        super().__init__(message)


class MissingSetupException(Exception):
    """
    Raised if an operation fails because setup has not been completed.
    """

    def __init__(self, message):
        super().__init__(message)


class MissingDeviceDataException(Exception):
    """
    An exception raised when a getter is called without enough information.
    """

    def __init__(self, required_info, cannot_get):
        self.message = f"Can't get {cannot_get} without the {required_info} attribute"
        super().__init__(self.message)


class NoIPFoundException(Exception):
    """
    An exception raised when an IP address could not be found.
    """

    def __init__(self, search_param):
        self.message = f"Could not find a device matching {search_param}"
        super().__init__(self.message)


class NoMACFoundException(Exception):
    """
    An exception raised when a MAC address could not be found.
    """

    def __init__(self, search_param):
        self.message = f"Could not find MAC address for device matching {search_param}"
        super().__init__(self.message)


class SSHNotReadyException(Exception):
    """
    An exception raised when an SSH operation is attempted on a device that is
    not ready for SSH.
    """

    def __init__(self, failed_operation, device):
        self.message = f"Could not connect to {device} via SSH to {failed_operation}"
        super().__init__(self.message)


class NoDeviceConfigException(Exception):
    """
    An exception raised when an operation attempts to retrive information from a
    device config file that does not exist.
    """

    def __init__(self, failed_operation, device):
        self.message = (
            f"{device} has no config file. Could not execute {failed_operation}"
        )
        super().__init__(self.message)
