import argparse
import os
import configparser
import paramiko


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("user_and_host")
    parser.add_argument("key_value_pairs", nargs="*")
    args = parser.parse_args()

    username, host = args.user_and_host.split("@")

    # Establish an SSH client
    ssh = paramiko.SSHClient()
    ssh.load_system_host_keys()
    ssh.set_missing_host_key_policy(paramiko.WarningPolicy)
    ssh.connect(host, username=username)

    # Create a new config parser object
    config = configparser.ConfigParser()

    # If the config file already exists, read it
    config_file = os.path.expanduser("~/.config/tracr")
    if os.path.exists(config_file):
        config.read(config_file)

    # Update the config with the provided key-value pairs
    if "DEFAULT" not in config:
        config.add_section("DEFAULT")
    for pair in args.key_value_pairs:
        key, value = pair.split("=")
        config.set("DEFAULT", key, value)

    # Write the config file
    with open(config_file, "w") as f:
        config.write(f)

    ssh.close()


if __name__ == "__main__":
    main()
