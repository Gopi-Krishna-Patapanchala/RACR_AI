import rpyc


# used to keep track of RPC servers that are up (and their services)
class ObserverRegistryServer(rpyc.utils.registry.UDPRegistryServer):
    pass


# used to coordinate with participant nodes
class ObserverService(rpyc.Service):
    def exposed_inference_completed_signal(self, uuid):
        # to be implemented by Steve
        pass
