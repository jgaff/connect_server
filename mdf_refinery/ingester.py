import json
import multiprocessing
from queue import Empty

from globus_sdk import GlobusAPIError

from mdf_toolbox import toolbox


NUM_SUBMITTERS = 5


def ingest(ingest_client, feedstock, batch_size=100):
    """Ingests feedstock from file.

    Arguments:
    ingest_client (SearchClient): An authenticated client (see mdf_forge.toolbox)
    feedstocks: (str or list of str or list of list of dict):
                    Path(s) to files containing feedstock,
                    or a list of lists of feedstock.
    batch_size (int): Max size of a single ingest operation. -1 for unlimited. Default 100.
    """
    # Fix single case of path not in list
    if isinstance(feedstock, str):
        feedstock = [feedstock]
    # Feedstock must be iterable of str, or iterable of iterable of dict
    if not hasattr(feedstock, "__iter__"):
        raise TypeError("feedstock must be an iterable")
    # If list of str, open paths
    if isinstance(feedstock[0], str):
        iter_stock = []
        for path in feedstock:
            iter_stock.append(open_feedstock(path))
    # Otherwise, ensure is list of iterables
    elif hasattr(feedstock[0], "__iter__"):
        iter_stock = feedstock
    else:
        raise TypeError("feedstock must be an iterable of iterables")

    # Set up multiprocessing
    ingest_queue = multiprocessing.JoinableQueue()
    killswitch = multiprocessing.Value('i', 0)

    # One reader
    reader = multiprocessing.Process(target=queue_ingests,
                                     args=(ingest_queue, iter_stock, batch_size))
    # As many submitters as is feasible
    submitters = [multiprocessing.Process(target=process_ingests,
                                          args=(ingest_queue, ingest_client, killswitch))
                  for i in range(NUM_SUBMITTERS)]
    reader.start()
    [s.start() for s in submitters]

    reader.join()
    ingest_queue.join()
    killswitch.value = 1
    [s.join() for s in submitters]

    return {"success": True}


def queue_ingests(ingest_queue, feedstocks, batch_size):
    for stock in feedstocks:
        list_ingestables = []
        for entry in stock:
            record = toolbox.format_gmeta(entry)
            list_ingestables.append(record)

            if batch_size > 0 and len(list_ingestables) >= batch_size:
                full_ingest = toolbox.format_gmeta(list_ingestables)
                ingest_queue.put(json.dumps(full_ingest))
                list_ingestables.clear()

        # Check for partial batch to ingest
        if list_ingestables:
            full_ingest = toolbox.format_gmeta(list_ingestables)
            ingest_queue.put(json.dumps(full_ingest))
            list_ingestables.clear()


def process_ingests(ingest_queue, ingest_client, killswitch):
    while killswitch.value == 0:
        try:
            ingestable = json.loads(ingest_queue.get(timeout=5))
        except Empty:
            continue
        try:
            res = ingest_client.ingest(ingestable)
            if not res["success"]:
                raise ValueError("Ingest failed: " + str(res))
            elif res["num_documents_ingested"] <= 0:
                raise ValueError("No documents ingested: " + str(res))
        except GlobusAPIError as e:
            print("\nA Globus API Error has occurred. Details:\n", e.raw_json, "\n")
            continue
        ingest_queue.task_done()


def open_feedstock(path):
    with open(path, "r") as feedstock_file:
        for json_entry in feedstock_file:
            yield json.loads(json_entry)
