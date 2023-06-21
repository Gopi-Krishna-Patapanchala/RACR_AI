# Setting up the Raspberry Pi 3 
1. Install the Raspbian Lite OS (headless)
2. Enable incoming SSH connections
3. Create a user profile specifically for the test bed
4. Configure /etc/dhcpcd.conf to allow gateway connections (if the LAN is not connected to the internet and will neet to use the controller device as a gateway)
5. Use the get-docker.sh script to install the Docker CE engine
6. Follow Docker's recommended post-installation steps to add the user to a security group for Docker so all commands don't need "sudo"
7. The Raspbian Lite OS does not enable cgroups for memory by default, which means Docker containers cannot have specific memory allocation limits set. To fix this, add `cgroup_enable=memory cgroup_memory=1 swapaccount=1` to the end of the single line in /boot/cmdline.txt, then reboot. Use the command `docker info` to check that it worked.
8. You may need to increase the size of the swapfile on Raspberry Pi devices to prevent OOM ("Out Of Memory") errors from killing your containers. To do this, stop swapping temporarily with the `sudo dphys-swapfile swapoff` command, then edit the `/etc/dphys-swapfile` file to set CONF_SWAPSIZE to the preferred size in megabytes. Then use `sudo dphys-swapfile setup` to create the new swapfile, and `sudo dphys-swapfile swapon` to start using it again. Reboot required to allow access to the new swapfile for running processes.
9. Set up passwordless SSH
