import sys
import logging
import os
import io
from concurrent import futures
import grpc
# from timeit import default_timer as timer
import time
# from time import perf_counter_ns as timer, process_time_ns as cpu_timer
from time import time as timer
import uuid
import pickle
import blosc2 as blosc
import numpy as np
from PIL import Image

sys.path.append(".")
parent = os.path.abspath('.')
sys.path.insert(1, parent)

import alexnet_pytorch_split as alex
from test_data import test_data_loader as data_loader

from . import colab_vision
from . import colab_vision_pb2
from . import colab_vision_pb2_grpc

class FileServer(colab_vision_pb2_grpc.colab_visionServicer):
    def __init__(self):

        class Servicer(colab_vision_pb2_grpc.colab_visionServicer):
            def __init__(self):
                self.tmp_folder = './temp/'
                self.model = alex.Model()
                # self.model = Model()

            def constantInference(self, request_iterator, context):
                #unpack msg contents
                current_chunks = []
                last_id = None
                for i, msg in enumerate(request_iterator):
                    # print(f"Message received with id {msg.id}.")
                    m = colab_vision_pb2.Response_Dict(
                            id = msg.id,
                            results = str(i).encode(),
                            actions = msg.action
                        )
                    if colab_vision_pb2.ACT_END in msg.action:
                        #hard exit, dont do it
                        raise Exception("Hard Exit called")
                    # if new id
                    if colab_vision_pb2.ACT_RESET in msg.action:
                        m.keypairs.clear()
                        current_chunks = []
                        last_id = msg.id
                        m.keypairs["server_start_time"] = time.time()
                    # rebuild data
                    if msg.id == last_id:
                        current_chunks.append(msg.chunk)
                    if colab_vision_pb2.ACT_APPEND in msg.action:
                        raise Exception("Append Unsupported")
                    if colab_vision_pb2.ACT_INFERENCE in msg.action:
                        print(len(current_chunks))
                        current_chunks = colab_vision.save_chunks_to_object(current_chunks)
                        print(len(current_chunks))
                        m.keypairs["server_assemble_time"] = time.time()
                        # decompress if needed
                        if colab_vision_pb2.ACT_COMPRESSED in msg.action:
                            current_chunks = blosc.unpack_tensor(current_chunks)
                            m.keypairs["server_compression_time"] = time.time() #not sure if this can even be done on instantiation
                        # start inference
                        prediction = self.model.predict(current_chunks, start_layer=msg.layer)
                        m.keypairs["server_inference_time"] = time.time()
                        # clean results
                        # m.keypairs["server_processing_time"] = time.time()
                    yield m

        logging.basicConfig()
        self.server = grpc.server(futures.ThreadPoolExecutor(max_workers=2))
        colab_vision_pb2_grpc.add_colab_visionServicer_to_server(Servicer(), self.server)

    def start(self, port):
        self.server.add_insecure_port(f'[::]:{port}')
        self.server.start()
        print("Server started.")
        self.server.wait_for_termination()