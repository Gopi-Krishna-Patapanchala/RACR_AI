import http.server
import socketserver
import oyaml
import logging
import json
import os
import sys
from pathlib import Path

import api.utils as utils
import api.bash_script_wrappers as bashw


logger = logging.getLogger("tracr_logger")


def serve_files_over_http(directory: Path, port: int = 8000):
    """
    Serves files from the specified directory over HTTP on the specified
    port. This is meant to be used by a data_loader on a remote machine.
    """

    def create_request_handler(dir: Path):
        """
        This is a factory for a simple HTTP request handler that serves files
        from a specified directory. It is meant to be used by a data_loader on a
        remote machine to load images from a local directory without taking
        up space on the remote machine unnecessarily. It extends the
        SimpleHTTPRequestHandler class from the builtin http.server module
        by adding a custom do_GET method that returns a list of files in the
        specified directory when the path is '/list_files', thus allowing
        the data_loader to know which files are available to load.
        """

        class FileRequestHandler(http.server.SimpleHTTPRequestHandler):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, directory=dir, **kwargs)

            def do_GET(self):
                if self.path == "/list_files":
                    self.send_response(200)
                    self.send_header("Content-type", "application/json")
                    self.end_headers()

                    files = os.listdir(directory)
                    self.wfile.write(json.dumps(files).encode())
                else:
                    super().do_GET()

        return FileRequestHandler

    handler = create_request_handler(directory)

    with socketserver.TCPServer(("", port), handler) as httpd:
        print(f"serving files from {directory} at port {port}.")
        httpd.serve_forever()


class Controller:
    """
    Represents the user's local machine. It is responsible for managing the
    participating devices, hosting the file transfer server(s), and collecting
    data about the experiment.
    """

    tracr_root: Path = utils.get_tracr_root()
    settings_fp: Path = tracr_root / "PersistentData" / "Configs" / "settings.yaml"
    data: dict

    def __init__(self):
        if not self.settings_fp.exists():
            raise FileNotFoundError("No settings file found.")
        else:
            self._read_settings()
            logger.info("Settings file found.")

    def _read_settings(self):
        """
        Internal function used to read the settings file to memory.
        """
        with open(self.settings_fp, "r") as f:
            self.data = oyaml.safe_load(f)

    def get_settings(self, category: str = None):
        """
        Returns the settings for the specified category. If no category is
        specified, returns all settings.
        """
        if not self.settings_fp.exists():
            raise FileNotFoundError("No settings file found.")
        with open(self.settings_fp, "r") as f:
            settings = oyaml.safe_load(f)
        if category:
            return settings[category]
        else:
            return settings

    def open_fileserver(self, directory, port=8000):
        """
        Opens that fileserver up there.
        """
        serve_files_over_http(directory, port)


if __name__ == "__main__":
    if not len(sys.argv) == 3:
        print("Usage: python3 controller.py <directory> <port>")
        sys.exit(1)

    directory = Path(sys.argv[1]).absolute()
    print(directory)
    port = int(sys.argv[2])

    serve_files_over_http(directory, port)
