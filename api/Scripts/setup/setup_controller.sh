#!/bin/bash

# Define the directory of this script
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Install dependencies for pyenv
echo ""
echo "------------------------------------"
echo "Installing dependencies for pyenv..."
echo "------------------------------------"
echo ""
sudo apt-get update -y && sudo apt-get upgrade -y
sudo apt-get install -y make build-essential libssl-dev zlib1g-dev libbz2-dev libreadline-dev libsqlite3-dev wget curl llvm libncurses5-dev libncursesw5-dev xz-utils tk-dev libffi-dev liblzma-dev python-openssl git

# Check if pyenv is already installed
if ! command -v pyenv &> /dev/null
then
    # install it
    echo ""
    echo "-------------------"
    echo "Installing pyenv..."
    echo "-------------------"
    echo ""
    curl -L https://pyenv.run | bash

    # Add pyenv to bashrc
    echo ""
    echo "-------------------------"
    echo "Adding pyenv to bashrc..."
    echo "-------------------------"
    echo ""
    echo 'export PYENV_ROOT="$HOME/.pyenv"' >> ~/.bashrc ~/.profile
    echo 'command -v pyenv >/dev/null || export PATH="$PYENV_ROOT/bin:$PATH"' >> ~/.bashrc ~/.profile
    echo 'eval "$(pyenv init -)"' >> ~/.bashrc ~/.profile
    echo 'eval "$(pyenv virtualenv-init -)"' >> ~/.bashrc
    echo "Done."

    # Apply the changes to the current shell
    export PYENV_ROOT="$HOME/.pyenv"
    command -v pyenv >/dev/null || export PATH="$PYENV_ROOT/bin:$PATH"
    eval "$(pyenv init -)"
fi

# Install Python 3.11.4 with pyenv
echo ""
echo "--------------------------------------"
echo "Installing Python 3.11.4 with pyenv..."
echo "--------------------------------------"
echo ""
pyenv install -s 3.11.4
echo "Done."

# Go to project root directory
cd "$DIR/../"

# Use pyenv to set Python version for this directory to 3.11.4
echo ""
echo "------------------------------------------------------"
echo "Setting Python version for this directory to 3.11.4..."
echo "------------------------------------------------------"
echo ""
pyenv local 3.11.4
echo "Done."

# Upgrade pip
echo ""
echo "----------------"
echo "Upgrading pip..."
echo "----------------"
echo ""
pip install --upgrade pip

# Install venv
echo ""
echo "------------------"
echo "Installing venv..."
echo "------------------"
echo ""
pip install virtualenv

# Create a new venv in the project root
echo ""
echo "------------------------------------------"
echo "Creating tracr-venv in the project root..."
echo "------------------------------------------"
echo ""
python -m venv tracr-venv
echo "Done."

# Activate the venv
echo ""
echo "----------------------"
echo "Activating the venv..."
echo "----------------------"
echo ""
source tracr-venv/bin/activate
echo "Done."

# Use pip to install dependencies from requirements.txt in project root
if [ -f requirements.txt ]; then
    echo ""
    echo "------------------------------------------------"
    echo "Installing dependencies from requirements.txt..."
    echo "------------------------------------------------"
    echo ""
    pip install -r requirements.txt
else
    echo ""
    echo "-------------------------------------------------------------------------------"
    echo "requirements.txt not found in project root. Skipping dependency installation..."
    echo "-------------------------------------------------------------------------------"
    echo ""
fi

# Deactivate the venv
echo ""
echo "------------------------"
echo "Deactivating the venv..."
echo "------------------------"
echo ""
deactivate
echo "Done."

echo ""
echo "-----------------------------"
echo "Setup completed successfully!"
echo "-----------------------------"
echo ""
