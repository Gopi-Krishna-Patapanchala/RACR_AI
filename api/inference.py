import uuid

class InferenceReport(dict):
    """
    Stores inference results and makes it easier to consolidate
    results from multiple nodes. Each inference may have multiple
    layers, and each layer may have multiple partitions, and thus
    multiple nodes.

    Instances of this class can be consolidated with the "+" operator.

    A "to_df" method is provided to convert the results to a pandas
    DataFrame. A single inference may be composed of many rows of data.
    Each partition (if it exists) will have its own row, and each layer
    may have multiple partitions. Of course, each inference will
    most likely have multiple layers.
    """

    id: uuid.UUID = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not (len(args) == 1 and isinstance(args[0], dict)):
            raise TypeError("InferenceReport must be initialized with a single dict")
        
        
            

        # inference_id follows form "<uuid>.<section>.[<partition>]"
        inference_id_parts = from_dict.get("inference_id", "").split(".")

            self.id = inference_id_parts[0]
            if len(inference_id_parts) > 1:
                section = int(inference_id_parts[1])
            if len(inference_id_parts) > 2:
                partition = int(inference_id_parts[2])