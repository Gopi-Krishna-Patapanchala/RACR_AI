import os
import configparser
import paramiko
import toml


DEVICE_CONFIG_FP = "~/.config/tracr"
ENSURE_CONFIG_DIR_CMD = "mkdir -p ~/.config"
GET_CONFIG_FILE_CONTENT_CMD = "cat ~/.config/tracr || echo ''"


class SSHCommandFailedException(Exception):
    """
    An exception raised when an SSH command is unsuccessful.
    """

    def __init__(self, host: str, command: str, err: str):
        self.message = f"SSH Command failed on {host} with command {command}\n{err}"
        super().__init__(self.message)


def write_device_config(username: str, host: str, update_dict: dict):
    """
    SSH into a device and look for a config file. If it's not there, make one. Then
    zip keylist and value list into a list of key, val tuples and add them to the
    config file if they are not there already. Overwrite keys that already exist but
    have a different value. Leave key-value pairs alone in they don't match any new
    pairs.

    Only supports one layer of nesting.
    """

    def ssh_command(ssh, command):
        stdin, stdout, stderr = ssh.exec_command(command)
        exit_status = stdout.channel.recv_exit_status()
        return exit_status == 0, stdout.read().decode(), stderr.read().decode()

    def update_config_file(ssh, update_dict, host):
        # Ensure the directory for the config file exists
        success, output, err = ssh_command(ssh, ENSURE_CONFIG_DIR_CMD)
        if not success:
            raise SSHCommandFailedException(host, GET_CONFIG_FILE_CONTENT_CMD, err)

        # Get the current config file content
        success, file_content, err = ssh_command(ssh, GET_CONFIG_FILE_CONTENT_CMD)
        if not success:
            raise SSHCommandFailedException(host, GET_CONFIG_FILE_CONTENT_CMD, err)

        # get toml file contents
        contents_as_dict = toml.loads(file_content)

        # update file contents (now stored as dict)
        for key, val in update_dict.items():
            if not isinstance(val, dict):
                contents_as_dict[key] = val
            else:
                subdict = contents_as_dict.get(key, None)
                if not subdict:
                    contents_as_dict[key] = {}
                for subkey, subval in val.items():
                    contents_as_dict[key][subkey] = subval

        # Write the updated config file content
        updated_string = toml.dumps(contents_as_dict)
        write_command = f"echo '{updated_string}' > ~/.config/tracr"
        success, output, err = ssh_command(ssh, write_command)
        if not success:
            raise SSHCommandFailedException(host, write_command, err)

    # Establish an SSH client
    ssh = paramiko.SSHClient()
    ssh.load_system_host_keys()
    ssh.set_missing_host_key_policy(paramiko.WarningPolicy)
    ssh.connect(host, username=username)

    # write changes to file
    update_config_file(ssh, update_dict, host)

    ssh.close()


if __name__ == "__main__":
    TEST_USERNAME = "racr"
    TEST_HOST = "192.168.1.251"
    TEST_UD = {
        "version": "0.0",
        "general": {"base_image_name": "raspberry-pi-4-base"},
        "resources": {"memory": "2g", "memory-swap": -1, "cpus": 1},
    }

    write_device_config(TEST_USERNAME, TEST_HOST, TEST_UD)
