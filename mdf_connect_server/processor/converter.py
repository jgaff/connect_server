from ctypes import c_bool
import json
import logging
import multiprocessing
import os
from queue import Empty

import mdf_toolbox

from mdf_connect_server.processor import transform


logger = logging.getLogger(__name__)


def convert(root_path, convert_params):
    """Convert files under the root path into feedstock.

    Arguments:
    root_path (str): The path to the directory holding all the dataset files.
    convert_params (dict): Parameters for conversion.
        dataset (dict): The dataset associated with the files.
        parsers (dict): Parser-specific parameters, keyed by parser (ex. "json": {...}).
        service_data (str): The path to a directory to store integration data.
        group_config (dict): Grouping configuration.
        num_transformers (int): The number of transformer processes to use. Default 1.

    Returns:
    list of dict: The full feedstock for this dataset, including dataset entry.
    """
    source_id = convert_params.get("dataset", {}).get("mdf", {}).get("source_id", "unknown")

    # Set up multiprocessing
    input_queue = multiprocessing.Queue()
    output_queue = multiprocessing.Queue()
    input_complete = multiprocessing.Value(c_bool, False)

    # Start up transformers
    transformers = [multiprocessing.Process(target=transform,
                                            args=(input_queue, output_queue,
                                                  input_complete, convert_params))
                    for i in range(convert_params.get("num_transformers", 1))]
    [t.start() for t in transformers]
    logger.debug("{}: Transformers started".format(source_id))

    # Populate input queue
    num_groups = 0
    extensions = set()
    for group_info in group_tree(root_path, convert_params["group_config"]):
        input_queue.put(group_info)
        num_groups += 1
        for f in group_info["files"]:
            filename, ext = os.path.splitext(f)
            extensions.add(ext or filename)
    # Mark that input is finished
    input_complete.value = True
    logger.debug("{}: Input complete".format(source_id))

    # Process dataset entry
    full_dataset = convert_params["dataset"]
    # Fetch custom block descriptors, cast values to str
    new_custom = {}
    # custom block descriptors
    # Turn _description => _desc
    for key, val in full_dataset.pop("custom", {}).items():
        if key.endswith("_description"):
            new_custom[key[:-len("ription")]] = str(val)
        else:
            new_custom[key] = str(val)
    for key, val in full_dataset.pop("custom_desc", {}).items():
        if key.endswith("_desc"):
            new_custom[key] = str(val)
        elif key.endswith("_description"):
            new_custom[key[:-len("ription")]] = str(val)
        else:
            new_custom[key+"_desc"] = str(val)
    if new_custom:
        full_dataset["custom"] = new_custom

    # Create complete feedstock
    feedstock = [full_dataset]
    while True:
        try:
            record = output_queue.get(timeout=1)
            feedstock.append(json.loads(record))
        except Empty:
            if any([t.is_alive() for t in transformers]):
                [t.join(timeout=1) for t in transformers]
            else:
                logger.debug("{}: Transformers joined".format(source_id))
                break

    return (feedstock, num_groups, list(extensions))


def group_tree(root, config):
    """Run group_files on files in tree appropriately."""
    files = []
    dirs = []
    if root == "/dev/null":
        return []
    for node in os.listdir(root):
        node_path = os.path.join(root, node)
        if node == "mdf.json":
            with open(node_path) as f:
                try:
                    new_config = json.load(f)
                    logger.debug("Config updating: \n{}".format(new_config))
                except Exception as e:
                    logger.warning("Error reading config file '{}': {}".format(node_path, str(e)))
                else:
                    config = mdf_toolbox.dict_merge(new_config, config)
        elif os.path.isfile(node_path):
            files.append(node_path)
        elif os.path.isdir(node_path):
            dirs.append(node_path)
        else:
            logger.debug("Ignoring non-file, non-dir node '{}'".format(node_path))

    # Group the files
    # list "groups" is list of dict, each dict contains actual file list + parser info/config
    groups = []
    # Group by dir overrides other grouping
    if config.get("group_by_dir"):
        groups.append({"files": files,
                       "parsers": [],
                       "params": {}})
    else:
        for format_rules in config.get("known_formats", {}).values():
            format_name_list = format_rules["files"]
            format_groups = {}
            # Check each file for rule matching
            # Match to appropriate group (with same pre/post pattern)
            #   eg a_[match]_b groups with a_[other match]_b but not c_[other match]_d
            for f in files:
                fname = os.path.basename(f).lower().strip()
                for format_name in format_name_list:
                    if format_name in fname:
                        pre_post_pattern = fname.replace(format_name, "")
                        if not format_groups.get(pre_post_pattern):
                            format_groups[pre_post_pattern] = []
                        format_groups[pre_post_pattern].append(f)
                        break
            # Remove grouped files from the file list and add groups to the group list
            for g in format_groups.values():
                for f in g:
                    files.remove(f)
                group_info = {
                    "files": g,
                    "parsers": format_rules["parsers"],
                    "params": format_rules["params"]
                }
                groups.append(group_info)

        # NOTE: Keep this grouping last!
        # Default grouping: Each file is a group
        groups.extend([{"files": [f],
                        "parsers": [],
                        "params": {}}
                       for f in files])

    [groups.extend(group_tree(d, config)) for d in dirs]

    return groups
