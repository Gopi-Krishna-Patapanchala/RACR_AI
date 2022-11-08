import sys
import logging
import os
import io
import grpc
# from timeit import default_timer as timer
# from time import perf_counter_ns as timer, process_time_ns as cpu_timer
# from time import time as timer
import time
import uuid
import pickle
import blosc2 as blosc
import numpy as np
from PIL import Image

from src.colab_vision import USE_COMPRESSION

sys.path.append(".")
parent = os.path.abspath('.')
sys.path.insert(1, parent)


from test_data import test_data_loader as data_loader
import alexnet_pytorch_split as alex

from . import colab_vision
from . import colab_vision_pb2
from . import colab_vision_pb2_grpc

class FileClient:
    def __init__(self, address):
        self.channel = grpc.insecure_channel(address)
        self.stub = colab_vision_pb2_grpc.colab_visionStub(self.channel)
        self.results_dict = {}
        logging.basicConfig()
        self.model = alex.Model()

    def safeClose(self):
        self.channel.close()
        for result, dic in self.results_dict.items():
            print(f"{result}:")
            for key, val in dic.items():
                print(f"\t{key}\t{val}")
        
    def initiateInference(self, target):
        #stuff
        messages = self.stub.constantInference(self.inference_generator(target))
        for received_msg in messages:
            # print(f"Received message from server for id:{received_msg.id} ")
            self.results_dict[received_msg.id]["client_complete_time"] = time.time()
            for key, val in received_msg.keypairs.items():
                self.results_dict[received_msg.id][key] = val

    def inference_generator_test(self, data_loader):
        for i in range(5):
            yield colab_vision_pb2.Info_Chunk(id = "test")

    def inference_generator(self, data_loader):
        print("image available.")
        tmp = data_loader.next()
        while(tmp):
            number_packets = 0
            try:
                [ current_obj, exit_layer, filename ] = next(tmp)
            except StopIteration:
                return
            message = colab_vision_pb2.Info_Chunk()
            message.ClearField('action')#colab_vision_pb2.Action()
            message.id = uuid.uuid4().hex # uuid4().bytes is utf8 not unicode like grpc wants
            message.layer = exit_layer + 1 # the server begins inference 1 layer above where the edge exited
            self.results_dict[message.id] = {} 
            self.results_dict[message.id]["filename"] = filename
            self.results_dict[message.id]["split_layer"] = exit_layer
            self.results_dict[message.id]["compression_level"] = "default"
            self.results_dict[message.id]["client_start_time"] = time.time()
            current_obj = self.model.predict(current_obj, end_layer=exit_layer)
            self.results_dict[message.id]["client_predict_time"] = time.time()

            message.ClearField('action')
            message.action.append(colab_vision_pb2.ACT_RESET)
            if colab_vision.USE_COMPRESSION:
                message.action.append(colab_vision_pb2.ACT_COMPRESSED)
                current_obj = blosc.pack_tensor(current_obj)
                self.results_dict[message.id]["client_compression_time"] = time.time()
            # send all pieces
            for i, piece in enumerate(colab_vision.get_object_chunks(current_obj)):
                message.chunk.CopyFrom(piece)
                if i == 1:
                    message.action.remove(colab_vision_pb2.ACT_RESET)
                # if piece is None: #current behavior will send the entirety of the current_obj, then when generator ends, follow up with action flags. small efficiency boost possible if has_next is altered
                #     message.action.append(3)
                    # print(f"total messages {i}")
                yield message
                number_packets += 1
            message.ClearField('chunk')
            # send blank message with process flag
            message.action.append(3)
            yield message
            number_packets += 1
            self.results_dict[message.id]["client_upload_time"] = time.time()
            self.results_dict[message.id]["client_number_packets"] = number_packets


    # def start(self, port):
    #     self.server.add_insecure_port(f'[::]:{port}')
    #     self.server.start()
    #     self.server.wait_for_termination()
