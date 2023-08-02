#!/bin/bash

# cd into the repo root
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )/../.." &> /dev/null && pwd )"

# Was the -d flag passed?
if [[ $1 == "-d" ]]; then

    # build the image using the dev Dockerfile
    docker build -t tracr-db -f "$DIR/Setup/Container/Dockerfile.dev" .

else

    # build the image using the prod Dockerfile
    docker build -t tracr -f "$DIR/Setup/Container/Dockerfile.prod" .

fi

exit $?
