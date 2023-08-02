import requests
from PIL import Image
from io import BytesIO


class DataLoader:
    """A very basic ABC for data loaders."""

    def __iter__(self):
        return self

    def __next__(self):
        return self.next()

    def has_next(self):
        raise Exception("not yet implemented")

    def next(self):
        raise Exception("not yet implemented")


class FileLoader(DataLoader):
    """
    Abstract base class for data loaders that load files from a directory.
    """

    def __init__(self):
        self.filepaths = []
        self.current_generator = None

    def has_next(self):
        # There are more items if there are more filepaths or there are more items in the current generator.
        return bool(len(self.filepaths)) or (self.current_generator is not None)

    def next(self):
        if self.current_generator is None or not self.has_next():
            if not self.has_next():
                raise StopIteration
            self.current_generator = self._get_next()
        try:
            return next(self.current_generator)
        except StopIteration:
            self.current_generator = None
            return self.next()

    def _get_filepaths(self):
        raise Exception("not yet implemented")

    def _get_next(self):
        raise Exception("not yet implemented")


class RemoteFileLoader(FileLoader):
    """
    Used in conjunction with an instance of FileRequestHandler running on the
    controller device to load files over HTTP rather than storing them locally.
    """

    def __init__(self, host="localhost", port=8000, mode="PIL-RGB"):
        super().__init__()
        self.server_address = f"http://{host}:{port}"
        self.mode = mode
        self._get_filepaths()
        self.current_file = None
        self.current_filename = None

    def next(self):
        return super().next()

    def _get_filepaths(self):
        self.filepaths = list(requests.get(f"{self.server_address}/list_files").json())

    def _get_next(self):
        while self.filepaths:
            self.current_filename = self.filepaths.pop(0)
            response = requests.get(f"{self.server_address}/{self.current_filename}")
            self.current_file = Image.open(BytesIO(response.content)).convert("RGB")
            if self.mode == "PIL-RGB":
                # simply yield images one at a time
                yield self.current_file
            elif self.mode == "OAS":
                # emulate behavior from the original alexnet split test_data_loader
                print(
                    f"Testing on image {self.current_filename}\t{len(self.filepaths)} remaining"
                )
                for i in range(1, 21):
                    print(f"\tLayer {i} split test in process")
                    yield [self.current_file, i, self.current_filename]
            else:
                raise ValueError(f"Invalid mode: {self.mode}")


if __name__ == "__main__":
    # Example usage:
    data_loader = RemoteFileLoader(mode="OAS")

    for val, split, fn in data_loader:
        print(f"Loaded image {fn} with split {split}")
