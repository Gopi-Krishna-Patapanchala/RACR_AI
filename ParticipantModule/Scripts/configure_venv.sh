#!/bin/bash

PYTHON_VERSION="3.11.4"
REQUIREMENTS_FP=$( realpath ~/.tracr/ParticipantModule/Setup/requirements.txt )
exit_code=0

# Function to handle the pyenv installation and global version setting
install_python_with_pyenv() {
    echo "Installing Python $PYTHON_VERSION with pyenv..."
    export PYENV_ROOT="$HOME/.pyenv"
    command -v pyenv >/dev/null || export PATH="$PYENV_ROOT/bin:$PATH"
    eval "$(pyenv init -)"
    pyenv install -s "$PYTHON_VERSION" || { exit_code=$(($exit_code | 1)); echo "Failed to install Python $PYTHON_VERSION"; }
    pyenv global "$PYTHON_VERSION" || { exit_code=$(($exit_code | 2)); echo "Failed to set Python $PYTHON_VERSION as global version"; }
}

# Function to upgrade pip
upgrade_pip() {
    echo "Upgrading pip to latest..."
    pip install --upgrade pip || { exit_code=$(($exit_code | 4)); echo "Failed to upgrade pip"; }
}

# Function to ensure virtualenv is installed
ensure_venv_installed() {
    echo "Ensuring venv is installed..."
    pip install virtualenv || { exit_code=$(($exit_code | 8)); echo "Failed to install virtualenv"; }
    pyenv virtualenv "$PYTHON_VERSION" participant-venv || { exit_code=$(($exit_code | 8)); echo "Failed to create virtualenv"; }
    pyenv global participant-venv || { exit_code=$(($exit_code | 8)); echo "Failed to set participant-venv as global version"; }
}

# Function to install dependencies from requirements.txt
install_requirements() {
    echo "Installing dependencies from requirements.txt..."
    if [ -f "$REQUIREMENTS_FP" ]; then
        pip install -r "$REQUIREMENTS_FP" || { exit_code=$(($exit_code | 16)); echo "Failed to install dependencies from requirements.txt"; }
    else
        echo "requirements.txt file not found. Skipping installation of dependencies."
        exit_code=$(($exit_code | 32))
    fi
}

# Main installation process
install_python_with_pyenv
ensure_venv_installed
upgrade_pip
install_requirements

echo "Done."
exit $exit_code
