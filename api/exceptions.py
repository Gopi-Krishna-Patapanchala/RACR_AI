class InvalidConfigFileException(Exception):
    """
    An exception raised when a config file is invalid.
    """

    def __init__(self, fp, message="Cannot load from invalid config file: "):
        self.message = message + fp
        super().__init__(self.message)


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
