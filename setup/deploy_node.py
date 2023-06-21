import argparse
import docker
import os
from docker.errors import ImageNotFound


def check_image(client, image_name):
    try:
        client.images.get(image_name)
        return True
    except ImageNotFound:
        return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("base_image_name")
    parser.add_argument("experiment_name")
    parser.add_argument("dockerfile_suffix")
    parser.add_argument("-p", "--port", default=None)
    parser.add_argument("-v", "--volume", default=None)
    parser.add_argument("-m", "--memory", default=None)
    parser.add_argument("--cpus", default=None)
    parser.add_argument("--use-swapfile", action="store_true")

    args = parser.parse_args()
    client = docker.from_env()

    if not check_image(client, args.base_image_name):
        print("Base image does not exist, building...")
        client.images.build(
            path=os.path.join(os.getcwd(), "setup", "BaseImages", args.base_image_name),
            tag=args.base_image_name,
        )

    print("Building second layer...")
    client.images.build(
        path=os.path.join(os.getcwd(), "TestCases", args.experiment_name),
        dockerfile=f"Dockerfile.{args.dockerfile_suffix}",
        tag=f"{args.experiment_name}-{args.dockerfile_suffix}",
        buildargs={"BASE_IMAGE": args.base_image_name},
    )

    print("Running the image...")
    volumes = (
        None
        if args.volume is None
        else {
            args.volume.split(":")[0]: {"bind": args.volume.split(":")[1], "mode": "rw"}
        }
    )
    ports = (
        None
        if args.port is None
        else {args.port.split(":")[1]: args.port.split(":")[0]}
    )
    mem_limit = None if args.memory is None else f"{args.memory}m"
    swap_mem = "0m" if args.use_swapfile else None

    container = client.containers.run(
        f"{args.experiment_name}-{args.dockerfile_suffix}",
        detach=True,
        ports=ports,
        volumes=volumes,
        mem_limit=mem_limit,
        cpuset_cpus=args.cpus,
        memswap_limit=swap_mem,
    )

    for line in container.logs(stream=True):
        print(line.strip())


if __name__ == "__main__":
    main()
