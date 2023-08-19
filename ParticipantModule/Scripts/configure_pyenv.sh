#!/bin/bash

echo "Adding pyenv settings to 'tracr' user's shell configs..."

# Initialize exit code
exit_code=0

# Function to add required lines to given file
add_pyenv_lines() {
    local file="$1"
    if ! grep -q 'export PYENV_ROOT=' "$file" 2>/dev/null; then
        echo 'export PYENV_ROOT="$HOME/.pyenv"' >> "$file" || { exit_code=$(($exit_code | 1)); echo "Failed to add PYENV_ROOT to $file"; }
        echo 'command -v pyenv >/dev/null || export PATH="$PYENV_ROOT/bin:$PATH"' >> "$file" || { exit_code=$(($exit_code | 2)); echo "Failed to add pyenv to PATH in $file"; }
        echo 'eval "$(pyenv init -)"' >> "$file" || { exit_code=$(($exit_code | 4)); echo "Failed to initialize pyenv in $file"; }
        echo 'eval "$(pyenv virtualenv-init -)"' >> "$file" || { exit_code=$(($exit_code | 8)); echo "Failed to initialize pyenv-virtualenv in $file"; }
    else
        echo "pyenv settings already exist in $file."
    fi
}

# Add required lines to .bashrc
add_pyenv_lines "$( realpath ~/.bashrc )"

# Check for existence of profile files and select the first one available
profile=""
for file in ~/.profile ~/.bash_profile ~/.bash_login; do
    if [ -e "$(realpath $file)" ]; then
        profile="$(realpath $file)"
        break
    fi
done

# If none exist, create ~/.profile and save that filepath
if [ -z "$profile" ]; then
    touch "$( realpath ~/.profile )"
    profile="$( realpath ~/.profile )"
fi

# Add required lines to selected profile file
add_pyenv_lines "$profile"

echo "Done."
exit $exit_code
