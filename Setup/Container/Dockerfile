# NOTE: this Dockerfile is called by the build_tracr.sh script, which is made
#       to cd into the repo's root directory before invoking this file. This
#       means that Docker's context is not in the same directory as this file.
#       Keep this in mind when reading the ADD, COPY, etc. commands below as
#       they might look broken if you're not aware of this.

# No need to make a tiny image since (presumably) the user's PC is not a RPi3
FROM python:3.11.4-bookworm

# Set the working directory in the container to /app
WORKDIR /app

# Install extra system dependencies
COPY ./Setup/Container/tracr_dependencies.txt .
RUN apt-get update
RUN bash -c "cat tracr_dependencies.txt | xargs apt-get install -y"

# Install necessary Python packages
COPY ./Setup/Container/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy over the API source code as well as the main app
# COPY ./api ./api    Commented out until the API and app are finished. Till then... it's a volume
# COPY app.py .

# Explicitly name the ports we'll have exposed (3 for now)
EXPOSE 9001
EXPOSE 9002
EXPOSE 9003

# Run the tracr application when launched
COPY ./Setup/Container/entrypoint.sh /
ENTRYPOINT [ "/entrypoint.sh" ]