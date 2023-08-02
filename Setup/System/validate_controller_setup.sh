#!/bin/bash

# Bit 0 (value 1) represents if the directory is NOT in the PATH
# Bit 1 (value 2) represents if Docker is NOT installed
# Bit 2 (value 4) represents if the user is NOT in the docker group
# If a bit is set (1), the corresponding check failed. If a bit is not set (0), the corresponding check is good.

# Get the absolute path to the repo root directory
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )/../.." &> /dev/null && pwd )"

# Initialize the exit code to 0
EXIT_CODE=0

# Check if the directory is in the PATH
if [[ ":$PATH:" != *":$DIR:"* ]]; then
    # Set bit 0
    EXIT_CODE=$((EXIT_CODE | 1))
fi

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    # Set bit 1
    EXIT_CODE=$((EXIT_CODE | 2))
fi

# Check if the user is in the docker group
if ! id -nG "$USER" | grep -qw docker; then
    # Set bit 2
    EXIT_CODE=$((EXIT_CODE | 4))
fi

# Return the exit code
exit $EXIT_CODE

