#!/bin/bash

# Get the absolute path to the repo root directory
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )/../.." &> /dev/null && pwd )"

# Check if the directory is in the PATH
if [[ ":$PATH:" != *":$DIR:"* ]]; then
    echo "Adding $DIR to PATH"
    # Backup .bashrc before modification with a timestamp
    cp ~/.bashrc ~/.bashrc_backup_$(date +%Y%m%d_%H%M%S)
    echo "export PATH=\$PATH:$DIR" >> ~/.bashrc
    PATH_UPDATED=true
else
    echo "$DIR is already in PATH"
    PATH_UPDATED=false
fi

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo "Docker is not installed"
    DOCKER_INSTALLED=false
else
    echo "Docker is already installed"
    DOCKER_INSTALLED=true
fi

if $DOCKER_INSTALLED; then
    # Check if the user is already in the docker group
    if ! id -nG "$USER" | grep -qw docker; then
        echo "Adding current user to docker group..."
        sudo usermod -aG docker $USER
        USER_ADDED_TO_DOCKER_GROUP=true
    else
        echo "Current user is already in docker group"
        USER_ADDED_TO_DOCKER_GROUP=false
    fi
fi

echo ""

if $DOCKER_INSTALLED; then
    echo "Setup successful."
    if $USER_ADDED_TO_DOCKER_GROUP; then
        echo "  The current user was added to the docker security group."
        echo "    Now you won't need to use sudo to run docker commands."
        echo "    Please log out and log back in for the changes to take effect."
    fi
    if $PATH_UPDATED; then
        echo "  The 'tracr' script was added to PATH."
        echo "    Now you can invoke the 'tracr' command from any directory."
        echo "    Please start a new shell session for the changes to take effect."
    fi
else
    echo "Setup failed."
    echo "  Please install Docker and try again."
fi
