#!/bin/bash

# Install pyenv
echo "Installing pyenv..."

if ! output=$(curl -L https://pyenv.run | bash 2>&1); then
    ECODE=$?
    echo "Failed to install pyenv: $output"
    exit $ECODE
else
    echo "$output"
    exit 0
fi