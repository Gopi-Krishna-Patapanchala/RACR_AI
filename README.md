# collaborative-vision-research
To run, start server and wait for warmup to complete before running client.

Inspiration from <https://github.com/gooooloo/grpc-file-transfer>
Info on pita from python grpc <https://news.ycombinator.com/item?id=21873468>
generated code imports must be converted to python 3 formatting, or some edit to the generation command is required
custom install of <https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2004/x86_64/libcudnn8_8.4.0.27-1+cuda11.6_amd64.deb>

<https://docs.nvidia.com/deeplearning/frameworks/install-tf-jetson-platform/index.html>
<https://github.com/microsoft/WSL/issues/4150#issuecomment-504209723>
<https://github.com/dusty-nv/jetson-containers>
<https://catalog.ngc.nvidia.com/orgs/nvidia/containers/l4t-ml>
<https://github.com/pjreddie/darknet/tree/master/src>
<https://github.com/zylo117/Yet-Another-EfficientDet-Pytorch>
<https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html>
<https://github.com/WongKinYiu/ScaledYOLOv4>
<https://paperswithcode.com/method/yolov4>
<>

## Changes introduced in the `refactor/test-platform-api` branch

### Overview
The `refactor/test-platform-api` branch reorganizes the repo structure to bundle new features into an API, implemented as a Python module that lives in the "api" directory. These new features are introduced this way to decouple the testing platform's functionality from the user interface itself, which will make it easier to test, update, and refactor parts of the system individually. For instance, the user interface will likely begin as a CLI, but if we'd like to build a GUI in the future, having a separate "back end" (the api) will make this much easier to do.


The testing platform's goal is to make it easier for users to set up experiments / test cases, monitor performance metrics both in real-time and with generated reports and data visualization, and save experiment configurations so they can be replicated on different systems. Ultimately, we hope this will allow us to experiment with new methods and record our results more efficiently.

### User Workflow
After cloning the repository, the user will likely have to run a setup script to populate a configuration file with the system and network info needed to run the testing platform locally. The configuration file is included in the `.gitignore` for security reasons and because it will need to store different information for each local environment.

One of the more tedious parts of collaborative DNN experimentation is network setup, so the testing platform offers device discovery features, helps with setting up socket connections, and allows users to persistently store any number of network configurations for repeated use. These network configurations will include necessary info about the **controller device** as well as each **edge device** it will need to communicate with on the LAN. After setting up and saving a new network configuration, re-establishing the connection should essentially be "one-click" (or perhaps a few key-presses while the interface is a CLI).

Once the user has run the setup script and saved their network configuration, they can begin running experiments. The user-provided code and configuration settings (e.g., on which device will each script be run, and in what order?) for each experiment will be stored in its own subdirectory within the "TestCases" directory.

To run an experiment, the system will first use Docker to load a **base image** specific to each involved device's architecture, containing some basic dependencies required for collaborative DNN inference and training - namely, *Python 3.6, blosc2, grpcio-tools, numpy, pandas, Pillow, protobuf, torch 1.10,* and *torchvision 0.11.1* . Next, any additional user-specified dependencies are added during the second-layer build, along with the actual user-provided runtime script for that machine. Finally, the script is executed within a built-in **wrapper script** responsible for tracking per-device performance metrics.

Because everything needed to run each experiment is containerized and stored in its own directory, replicating experiments on new systems should be straightforward. Experiment results, including both prediction data and performance metrics, are stored in a log file that can be parsed to generate reports and data visualizations. It would likely be worthwhile to structure these subdirectories within "TestCases" in a way that allows users to easily share experiments with other users.

### API Component Structure
Like previously mentioned, the API serves as a "back end" that is fully decoupled from the user interface itself. It can be though of in terms of its three main functions: networking, experiment setup, and performance tracking / reporting.

#### Networking
Each node in a given network will be represented by a certain class implemented in the `network.py` file. Currently, there are three classes implemented in this file:

1. **Device**: This class represents any type of device on the network. It can be instantiated as an "unconfigured" device, then be set up one step at a time (as would be the case for new devices), or it can be instantiated using saved data if it has been configured previously. It stores relevant attributes like IP, MAC address, architecture, OS family, etc. It also provides methods for getting the previously mentioned information, establishing a connection via SSH, syncing data from the controller device, saving and editing data, and running containers.

2. **Controller**: This class represents the network's "controller device", which is the device the user is working on. It is a child class of `Device`, inheriting most of the same functionality while also adding attributes and methods required to manage the other devices, like operating as an SSH client and launching test cases from its local repository.

3. **LAN**: This class represents the network itself, or more specifically, a particular network configuration. If two separate users were to use the same network at different times, they'd have two different `LAN` instances because the controller device info almost certainly wouldn't match. The `LAN` class has an associative relationship with `Device` and `Controller`, storing any number of `Device` instances and one `Controller` instance as attributes. It provides methods for device discovery, editing network settings, saving configuration data, and orchestrating container deployment according to user-defined constraints. (e.g., to which devices and in what order containers are deployed).

#### Experiment Setup

##### Custom Utility Scripts (implemented)
A few utility scripts have been implemented using bash to make it easier to interface with the IoT devices (RPi3s, Jetson Nanos) from a PC. These will be used by the API to perform certain networking tasks and Docker commands necessary for running experiments.
1. **open_gateway.sh**: Allows the IoT devices in the CS Lab LAN to access the internet using your PC as a gateway. Helpful for installing new software or updates.
2. **sync_repos.sh**: Quickly syncs changes made to the collab-vision repo on your local machine to all IoT devices in the LAN.
3. **deploy_node.sh**: Deploys a containerized "node" for testing as either a remote or client device. Pass option flags to determine which base image to use, depending on the architecture and hardware of the node. It also gives you the ability to run any image in "Interactive Terminal" mode so you can use a terminal from inside the running container, test, and poke around for troubleshooting.
4. **deploy_swarm.sh**: (Not finished) Deploys a cluster of edge devices using Docker Swarm. May be useful in the future if we need to use Docker Swarm's logging features down the line.

##### The `Experiment` class (not implemented)
Each test case / experiment is stored in its own subdirectory within the "TestCases" directory. Using the code and configuration data within this subdirectory, experiments can be represented and controlled using a Python class. Although much of the required functionality has been implemented using bash scripts, this class has not yet been implemented. However, it will follow this general outline:

The `Experiment` class, implemented in the `experiment.py` file, is responsible for the setup and execution of experiments. This class represents a test case that the user wants to run on the network. It includes relevant attributes like:

1. **Experiment ID**: A unique identifier for the experiment assigned during creation.
2. **Devices**: A collection of device constraints (NOT device instances) that outlines the number of devices required and each device's type, dependencies outside of the base image, runtime script, and order of deployment.
3. **Experiment Configuration**: This includes all settings and parameters required to replicate the experiment. It can be serialized into a JSON file to make the experiment portable and easy to share.
4. **Log File**: A file where all experiment outputs, including results and performance metrics, are stored for further analysis.

This class also provides methods to validate the experiment setup, build and execute Docker containers on the devices, monitor the execution progress, save its own configuration persistently, and handle output logging.

#### Performance Tracking and Reporting
The performance tracking, reporting, and data visualization functionality of the testing platform have not yet been implemented, but will follow this general outline:

1. During the final stage of a container's build process (Layer 3), a wrapper script calling the user-specified code will be set as the container's runtime command. This wrapper script will track the PID of each process (and subproccess) invoked by the user-provided code.
2. Using either A.) standard process monitoring tools built into the operating system or B.) third-party tools that must be added to each architecture's base image, the wrapper script will either continuously make system calls or parse through system logs to retrieve performance metrics like execution time, network throughput, power consumption, memory usage, clock cycles, etc.
3. The wrapper script will write all retrieved data to a file in the "Logs" directory
4. A `Performance` class will manage data retrieval and report generation, allowing users to export data in .csv, .xlsx, JSON, or pickled DataFrame / ndarray format.
5. This processed data will be perfect for creating visualizations, but this will likely be implemented in a separate class/component.

