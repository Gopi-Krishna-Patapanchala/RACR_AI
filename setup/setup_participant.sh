#!/bin/bash

# Function to delete the 'tracr' user and its home directory
function uninstall {
    echo "Removing 'tracr' user and its associated data..."
    sudo deluser --remove-home tracr
    sudo rm /etc/sudoers.d/tracr
    echo "User 'tracr' and its associated data have been deleted."
    exit 0
}

# Check if -u flag is passed
while getopts u flag
do
    case "${flag}" in
        u) uninstall;;
    esac
done

# Your previous script starts here
# Create user "tracr" and prompt for password
echo ""
echo "----------------------------"
echo "Creating new user 'tracr'..."
echo "----------------------------"
echo ""
sudo adduser tracr --gecos "First Last,RoomNumber,WorkPhone,HomePhone" --disabled-password
echo "tracr:tracr" | sudo chpasswd

# Give the user sudo permissions without password
echo ""
echo "---------------------------------------"
echo "Giving 'tracr' user sudo permissions..."
echo "---------------------------------------"
echo ""
echo "tracr ALL=(ALL) NOPASSWD: ALL" | sudo tee /etc/sudoers.d/tracr

# Install dependencies for pyenv
sudo apt-get update -y && sudo apt-get upgrade -y
sudo apt-get install -y make build-essential libssl-dev zlib1g-dev libbz2-dev libreadline-dev libsqlite3-dev wget curl llvm libncurses5-dev libncursesw5-dev xz-utils tk-dev libffi-dev liblzma-dev python-openssl git

# Install uuid-runtime to assign uuid to device
sudo apt-get install -y uuid-runtime

# Switch to 'tracr' user and install pyenv
sudo su - tracr <<'EOF'

# Ensure 'tracr' account is accessible via SSH
echo ""
echo "-------------------------------------------------"
echo "Ensuring 'tracr' account is accessible via SSH..."
echo "-------------------------------------------------"
echo ""
sudo systemctl enable ssh
sudo systemctl start ssh

# Install pyenv
echo ""
echo "-------------------"
echo "Installing pyenv..."
echo "-------------------"
echo ""
curl -L https://pyenv.run | bash

# Add pyenv to bashrc
echo ""
echo "----------------------------------------"
echo "Adding pyenv to 'tracr' user's bashrc..."
echo "----------------------------------------"
echo ""
echo 'export PYENV_ROOT="$HOME/.pyenv"' >> ~/.bashrc
echo 'export PYENV_ROOT="$HOME/.pyenv"' >> ~/.profile
echo 'command -v pyenv >/dev/null || export PATH="$PYENV_ROOT/bin:$PATH"' >> ~/.bashrc
echo 'command -v pyenv >/dev/null || export PATH="$PYENV_ROOT/bin:$PATH"' >> ~/.profile
echo 'eval "$(pyenv init -)"' >> ~/.bashrc
echo 'eval "$(pyenv init -)"' >> ~/.profile
echo 'eval "$(pyenv virtualenv-init -)"' >> ~/.bashrc
echo "Done."

# Create directories in user's home
echo ""
echo "----------------------------------------"
echo "Creating directories for 'tracr' user..."
echo "----------------------------------------"
echo ""
mkdir -p ~/.tracr/experiments
mkdir -p ~/.tracr/device_info
echo "Done."

# Generate UUID and write to file
echo ""
echo "---------------------------------------------"
echo "Generating device UUID and writing to file..."
echo "---------------------------------------------"
echo ""
UUID=$(uuidgen)
echo $UUID | sudo -u tracr tee /home/tracr/.tracr/device_info/my_uuid.txt > /dev/null
echo "Done."

EOF

# Run the rest of the script as 'tracr'
sudo -H -u tracr bash -l - <<'EOF'

# Install python 3.8.17 using pyenv and set it as global version
echo ""
echo "--------------------------------------"
echo "Installing Python 3.8.17 with pyenv..."
echo "--------------------------------------"
echo ""
export PYENV_ROOT="$HOME/.pyenv"
command -v pyenv >/dev/null || export PATH="$PYENV_ROOT/bin:$PATH"
eval "$(pyenv init -)"
pyenv install -s 3.8.17
pyenv global 3.8.17
echo "Done installing Python 3.8.17."

# upgrade pip
echo ""
echo "--------------------------"
echo "Upgrading pip to latest..."
echo "--------------------------"
echo ""
pip install --upgrade pip

# Ensure venv is installed
echo ""
echo "-----------------------------"
echo "Ensuring venv is installed..."
echo "-----------------------------"
echo ""
pip install virtualenv

EOF

echo "Setup completed successfully!"
