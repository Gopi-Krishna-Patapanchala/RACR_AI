#!/bin/bash

# cd into the repo root
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )/../.." &> /dev/null && pwd )"

# building the image from this context requires -f flag
docker build -t tracr -f "$DIR/Setup/Container/Dockerfile" .