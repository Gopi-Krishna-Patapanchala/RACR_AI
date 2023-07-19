import inspect
import subprocess
from pathlib import Path

import api.utils as utils

# Constants
PROJECT_ROOT = utils.get_tracr_root()


def validate_node_setup(
    experiment_name: str,
    node_type: str,
    python_version: str,
    pip_version: str,
    main_script_name: str,
    remote_host: str = None,
) -> dict:
    """
    Check if a node-type for an experiment is ready for deployment on either
    the local machine (controller) or a remote device (participant).

    Parameters
    ----------
    experiment_name : str
        Name of the experiment as it appears in the TestCases directory
    node_type : str
        The node type as it appears in the NodeTypes subdirectory of the
        experiment
    python_version : str
        The version of python to use for the node
    pip_version : str
        The version of pip to use for the node
    main_script_name : str
        The name of the main script for the node
    remote_host : str, optional
        The name of the remote host to check, by default None, which
        indicates that the check should be run on the local machine

    Returns
    -------
    results : dict
        A dictionary of booleans indicating the results of the checks. If
        the check was successfull, all values will be True.
    """
    script_filepath = PROJECT_ROOT / "api" / "Scripts" / "validate_node_setup"

    # tuple of predicates that will be checked by the check_venv script
    checks = (
        "base_dir_exists",
        "pyenv_file_exists",
        "requirements_file_exists",
        "main_script_exists",
        "src_dir_exists",
        "venv_activation_success",
        "python_versions_match",
        "required_packages_installed",
    )

    # assemble the args that will be passed to check_venv
    script_args = []
    if remote_host:
        for term in ("-r", remote_host):
            script_args.append(term)
    for arg in (
        experiment_name,
        node_type,
        python_version,
        pip_version,
        main_script_name,
    ):
        script_args.append(arg)

    return utils.run_bash_script_and_return_results(
        script_filepath, script_args, checks, invert_bits=True
    )


def node_setup(
    host: str,
    experiment_name: str,
    node_type: str,
    python_version: str,
    pip_version: str,
    overwrite: bool = False,
) -> dict:
    """
    Sets up a remote node using the information contained in the experiment
    directory found in the controller's local TestCases directory.

    Parameters
    ----------
    host : str
        The name of the remote host to setup
    experiment_name : str
        Name of the experiment as it appears in the TestCases directory
    node_type : str
        The node type as it appears in the NodeTypes subdirectory of the
        experiment
    python_version : str
        The version of python to use for the node
    pip_version : str
        The version of pip to use for the node
    overwrite : bool, optional
        Whether or not to overwrite an existing node, by default False

    Returns
    -------
    results : dict
        A dictionary of booleans indicating the potential errors during setup.
        If the setup was successfull, all values will be False.
    """
    script_filepath = PROJECT_ROOT / "api" / "Scripts" / "node_setup"

    # tuple of possible errors that could be returned by the script
    errors = (
        "cannot_overwrite",
        "rsync_failed",
        "python_install_failed",
        "venv_creation_failed",
        "pip_update_failed",
        "dependency_install_failed",
    )

    # assemble the args that will be passed to node_setup
    script_args = []
    if overwrite:
        script_args.append("-o")
    for arg in (
        host,
        experiment_name,
        node_type,
        python_version,
        pip_version,
    ):
        script_args.append(arg)

    return utils.run_bash_script_and_return_results(
        script_filepath, script_args, errors
    )


def participant_bootstrap(host: str, uninstall: bool = False) -> dict:
    """
    Wraps the setup_remote script to prepare a participant device for use with
    tracr by connecting over SSH. The device must already be configured in the
    user's ~/.ssh/config file.

    Parameters:
    -----------
    host : str
        The name of the host in the user's ~/.ssh/config file

    Returns:
    --------
    dict
        A dictionary describing the success/failure of the operation
    """
    script_filepath = (
        PROJECT_ROOT / "api" / "Scripts" / "setup" / "participant_bootstrap"
    )

    # tuple of stages that the script will progress through
    stages = (
        "tracr_user_creation_or_destruction",
        "build_dependency_installation",
        "ssh_configuration",
        "pyenv_installation",
        "pyenv_shell_setup",
        "tracr_datadir_creation",
        "python_installation",
        "python_package_installation",
    )

    # assemble the script args that will be passed to setup_remote
    script_args = []
    script_args.append(host)
    if uninstall:
        script_args.append("-u")

    return utils.run_bash_script_and_return_results(
        script_filepath, script_args, stages
    )


def validate_controller_setup(showprogress: bool = False) -> dict:
    """
    Wraps the validate_controller_setup script to check that the controller is
    ready for use with tracr.

    Parameters:
    -----------
    showprogress : bool, optional
        Whether or not to show the progress bar, by default False

    Returns:
    --------
    dict
        A dictionary describing the success/failure of each check
    """
    script_filepath = (
        PROJECT_ROOT / "api" / "Scripts" / "setup" / "controller" / "controller_setup"
    )

    checks = (
        "tracr_system_dependencies",
        "pyenv_configuration",
        "python_version_installation",
        "tracr-venv_configuration",
        "tracr_datadir_creation",
    )

    if showprogress:
        progressbar = {"task": "Validating controller setup...", "color": "cyan"}
    else:
        progressbar = None

    return utils.run_bash_script_and_return_results(
        script_filepath, ["-q"], checks, invert_bits=True, progress_bar=progressbar
    )


def validate_participant_setup(name: str, hostname_or_ip: str) -> dict:
    """
    Wraps the validate_participant_ssh_config and validate_participant_sys_setup
    scripts to check that the participant is ready for use with tracr.

    Parameters:
    -----------
    host : str
        The name of the host in the user's ~/.ssh/config file
    hostname_or_ip : str
        The hostname or IP address of the participant

    Returns:
    --------
    dict
        A dictionary describing the success/failure of each check
    """
    ssh_config_script_filepath = (
        PROJECT_ROOT
        / "api"
        / "Scripts"
        / "setup"
        / "src"
        / "validate_participant_ssh_config"
    )
    sys_setup_script_filepath = (
        PROJECT_ROOT
        / "api"
        / "Scripts"
        / "setup"
        / "src"
        / "validate_participant_sys_setup"
    )

    ssh_results = utils.run_bash_script_and_return_results(
        ssh_config_script_filepath,
        [name, hostname_or_ip],
        ["ssh_config_ok"],
        invert_bits=True,
    )
    sys_checks = (
        "tracr_user_exists",
        "tracr_system_dependencies",
        "ssh_enabled",
        "pyenv_configuration",
        "pyenv_shell_configs",
        "data_dirs_exist",
        "python_version_installation",
        "python_package_installation",
    )
    sys_results = utils.run_bash_script_and_return_results(
        sys_setup_script_filepath, [name, hostname_or_ip], sys_checks, invert_bits=True
    )

    # add granularity to permission errors
    ssh_results["ssh_validation_script_permissions_ok"] = ssh_results["permission_ok"]
    del ssh_results["permission_ok"]
    sys_results["sys_validation_script_permissions_ok"] = sys_results["permission_ok"]
    del sys_results["permission_ok"]
    sys_results.update(ssh_results)
    return sys_results


if __name__ == "__main__":
    # Arg sets that can be used
    LOCAL_CHECKNODE_OASR = (
        "OGAlexnetSplit",
        "Remote",
        "3.8.17",
        "21.3.1",
        "run_server.py",
    )
    REMOTE_CHECKNODE_OASC = (
        "OGAlexnetSplit",
        "Client",
        "3.8.17",
        "21.3.1",
        "run_client.py",
    )

    def show_checknode(e, n, py, pip, m, r=False):
        res = validate_node_setup(e, n, py, pip, m, remote_host=r)
        print(f"CheckNode Results for {e}: {n} ({'remote' if r else 'local'}):")
        for flag, bit in res.items():
            print(f"{flag}: {bit}")
        print("")

    print(f"\nProject Root (run as main): {PROJECT_ROOT}\n")

    for i, j in validate_controller_setup().items():
        print(f"{i}: {j}")

    show_checknode(*LOCAL_CHECKNODE_OASR)
    show_checknode(*REMOTE_CHECKNODE_OASC, r="home-pi-tracr")

    if not all(
        validate_node_setup(
            *REMOTE_CHECKNODE_OASC, remote_host="home-pi-tracr"
        ).values()
    ):
        print("\nRemote node not ready - setting up now...\n")
        res = node_setup("home-pi-tracr", *REMOTE_CHECKNODE_OASC[:-1], overwrite=True)

        for i, j in res.items():
            print(f"{i}: {j}")
        print("")

        show_checknode(*REMOTE_CHECKNODE_OASC, r="home-pi-tracr")
