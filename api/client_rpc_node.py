import rpyc
import uuid
import torch
import argparse
from rpyc.utils.server import ThreadedServer
from rpyc.utils.helpers import classpartial


class ParticipantService(rpyc.Service):
    def __init__(self, ident, input_dict) -> None:
        self.ident = ident
        self.results_dict = input_dict

    def on_connect(self, conn):
        # code that runs when a connection is created
        # (to init the service, if needed)
        pass

    def on_disconnect(self, conn):
        # code that runs after the connection has already closed
        # (to finalize the service, if needed)
        pass

    def exposed_tensor_mm(
        self, tensor1: torch.Tensor, tensor2: torch.Tensor
    ) -> torch.Tensor:
        """Very basic way to check whether torch is working on the server."""
        return torch.mm(tensor1, tensor2)

    def exposed_get_inference(self, uuid):  # this is an exposed method
        return self.results_dict.pop(uuid, [])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Start the ParticipantService RPC server."
    )
    parser.add_argument("port", type=int, help="Port number for the RPC server")
    args = parser.parse_args()

    rpc_service = classpartial(ParticipantService, ident=uuid.uuid4(), input_dict={})
    node1 = ThreadedServer(rpc_service, port=args.port)
    print(f"Starting server on port {args.port}")
    node1.start()
