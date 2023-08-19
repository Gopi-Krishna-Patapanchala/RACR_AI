#!/bin/bash

# Manually activate pyenv because it doesn't work in a script
export PYENV_ROOT="$HOME/.pyenv"
command -v pyenv >/dev/null || export PATH="$PYENV_ROOT/bin:$PATH"
eval "$(pyenv init -)"
eval "$(pyenv virtualenv-init -)"

# Make sure the virtualenv is activated
pyenv activate participant-venv

# Forward arguments to this script to the python script
nohup python3 ~/.tracr/ParticipantModule/Scripts/client_rpc_node.py "$@" &> /dev/null &