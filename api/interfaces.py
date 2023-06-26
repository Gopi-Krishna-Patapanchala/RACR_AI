class Storable:
    """
    Trying to make Python be more like Java. (Never though I'd see the day).
    """

    def attributes_as_dict(self):
        # Return the attribute_name - attribute_value pairs in a dict
        return {
            attr: getattr(self, attr)
            for attr in dir(self)
            if not attr.startswith("__") and not callable(getattr(self, attr))
        }

    def as_json_object(self):
        raise NotImplementedError("This method must be implemented by subclasses.")


class DeviceBlueprints:
    """
    The interface between network.Device and the config manager. Keeps things decoupled.
    """

    def __init__(self, attribute_dict: dict):
        pass
