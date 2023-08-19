#!/bin/bash

# Make sure the script is being run by the root user or with sudo privileges
if [[ $EUID -ne 0 ]]; then
   echo "This script must be run as root or with sudo privileges."
   exit 1
fi

# Update the local package database
apt-get update

# Check if the update was successful
if [ $? -eq 0 ]; then
  echo "Package database updated successfully!"
else
  echo "Failed to update the package database. Exiting."
  exit 1
fi

# Upgrade all packages
echo "Upgrading packages..."
apt-get upgrade -y

# Check if the upgrade was successful
if [ $? -eq 0 ]; then
  echo "Packages upgraded successfully!"
else
  echo "Failed to upgrade packages. Exiting."
  exit 1
fi

# Clean up unnecessary packages and dependencies
echo "Cleaning up unnecessary packages and dependencies..."
apt-get autoremove -y
apt-get autoclean -y

echo "Update process complete!"
