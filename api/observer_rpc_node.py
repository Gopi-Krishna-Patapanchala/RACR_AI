import rpyc
import datetime
import atexit
import threading
import api.utils as utils
import pandas as pd


class ObserverServer(rpyc.utils.registry.UDPRegistryServer):
    pass


class ObserverService(rpyc.Service):
    def __init__(self):
        self.finished_inference_queue = []
        self.queue_lock = threading.Lock()  # Lock for thread safety
        self.default_logfile_dir = utils.get_tracr_root() / "node_runner" / "output"
        self.report_df = pd.DataFrame(
            {"uuid": [], "split_layer": [], "inference_time": []}
        )
        atexit.register(self.write_inf_report)
        self.processing_thread = threading.Thread(target=self.process_queue)
        self.processing_thread.start()
        print("Started Observer Service.")

    def on_connect(self, conn):
        # code that runs when a connection is created
        pass

    def on_disconnect(self, conn):
        # code that runs after the connection has already closed
        # (to finalize the service, if needed)
        pass

    def process_queue(self):
        while True:
            with self.queue_lock:  # thread safety
                if self.finished_inference_queue:
                    self.fetch_and_consolidate_next_inf()

    def fetch_and_consolidate_next_inf(self):
        # Not exposed; get inference dicts from the participant nodes and consolidate them
        uuid = self.finished_inference_queue.pop(0)
        active_nodes = [
            (host, port)
            for service in rpyc.list_services()
            for host, port in rpyc.discover(service)
        ]

        dicts_to_consolidate = []
        for host, port in active_nodes:
            conn = rpyc.connect(host, port)
            # walrus operator can be read like " , which has the value "
            if serialized_dict := conn.root.get_inference_dict(uuid):
                dicts_to_consolidate.append(serialized_dict)

        result = {
            "sections": [],
            "layers": [],
            "split_layer": None,
            "inference_time": None,
        }
        for d in dicts_to_consolidate:
            result["sections"].append(
                {k: v for k, v in d.items() if k != "layer_information"}
            )
            result["layers"].extend(d["layer_information"])

        # Sum up all attributes with the word "time" in the key
        section_time = sum(
            [sum([v for k, v in d.items() if "time" in k]) for d in result["sections"]]
        )
        layer_time = sum(
            [v for layer in result["layers"] for k, v in layer.items() if "time" in k]
        )
        result["inference_time"] = section_time + layer_time

        result["split_layer"] = min(
            [
                exit_layer
                for section in result["sections"]
                for exit_layer in section["exit_layer"]
            ]
        )

        self.report_df = self.report_df.append(
            {
                "uuid": uuid,
                "split_layer": result["split_layer"],
                "inference_time": result["inference_time"],
            },
            ignore_index=True,
        )

    def write_inf_report(self, consolidated_inf_dict, dir=None, filename=None):
        # convert the consolidated inference dict to a single row of a csv and write it to a file
        if not dir:
            dir = self.default_logfile_dir
        if not filename:
            filename = f'{datetime.now().strftime("%Y-%m-%d_%H-%M-%S")}.csv'

        # write report_df to csv
        self.report_df.to_csv(dir / filename, index=False)

    def exposed_inference_completed_signal(self, uuid):
        with self.queue_lock:  # Ensure thread safety
            self.finished_inference_queue.append(uuid)
        print(f"Received inference completed signal for {uuid}")
