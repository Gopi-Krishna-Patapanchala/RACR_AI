#!/bin/bash

# path to list of dependencies
DEPENDENCIES_FILE=$(realpath ~/.tracr/ParticipantModule/Setup/participant_system_dependencies.txt)

# Check if the script is being run as root
if [ "$(id -u)" != "0" ]; then
  echo "This script must be run as root!"
  exit 1
fi

# Check if the file participant_system_dependencies.txt exists
if [ ! -f $DEPENDENCIES_FILE ]; then
  echo "File participant_system_dependencies.txt not found!"
  exit 1
fi

# Update package lists
echo "Updating package lists..."
apt-get update

# Read packages from participant_system_dependencies.txt and install each one
while read -r package; do
  if [ ! -z "$package" ]; then
    echo "Installing package $package..."
    apt-get install -y $package
  fi
done < $DEPENDENCIES_FILE

echo "All packages have been installed successfully!"
