import json
import sys
import os

from mdf_refinery.parsers.ase_parser import parse_ase
from tqdm import tqdm

from mdf_forge import toolbox
from mdf_refinery.validator import Validator

# VERSION 0.4.0

# Arguments:
#   input_path (string): The file or directory where the data resides.
#       NOTE: Do not hard-code the path to the data in the converter (the filename can be hard-coded, though). The converter should be portable.
#   metadata (string or dict): The path to the JSON dataset metadata file, a dict or json.dumps string containing the dataset metadata, or None to specify the metadata here. Default None.
#   verbose (bool): Should the script print status messages to standard output? Default False.
#       NOTE: The converter should have NO output if verbose is False, unless there is an error.
def convert(input_path, metadata=None, verbose=False):
    if verbose:
        print("Begin converting")

    # Collect the metadata
    # Fields can be:
    #    REQ (Required, must be present)
    #    RCM (Recommended, should be present if possible)
    #    OPT (Optional, can be present if useful)
    # NOTE: For fields that represent people (e.g. mdf-data_contact), other IDs can be added (ex. "github": "jgaff").
    #    It is recommended that all people listed in mdf-data_contributor have a github username listed.
    #
    # If there are other useful fields not covered here, another block (dictionary at the same level as "mdf") can be created for those fields.
    # The block must be called the same thing as the source_name for the dataset.
    if not metadata:
        ## Metadata:dataset
        dataset_metadata = {
            # REQ dictionary: MDF-format dataset metadata
            "mdf": {

                # REQ string: The title of the dataset
                "title": "H Projectile in Si: Channel Trajectories",

                # REQ list of strings: The UUIDs allowed to view this metadata, or 'public'
                "acl": ["public"],

                # REQ string: A short version of the dataset name, for quick reference. Spaces and dashes will be replaced with underscores, and other non-alphanumeric characters will be removed.
                "source_name": "schleife_stopping_proton",

                # REQ dictionary: The contact person/steward/custodian for the dataset
                "data_contact": {

                    # REQ string: The person's given (or first) name
                    "given_name": "Andre",

                    # REQ string: The person's family (or last) name
                    "family_name": "Schleife",

                    # REQ string: The person's email address
                    "email": "schleife@illinois.edu",

                    # RCM string: The primary affiliation for the person
                    "institution": "University of Illinois Urbana-Champaign",

                },

                # REQ list of dictionaries: The person/people contributing the tools (harvester, this converter) to ingest the dataset
                "data_contributor": [{

                    # REQ string: The person's given (or first) name
                    "given_name": "Jonathon",

                    # REQ string: The person's family (or last) name
                    "family_name": "Gaff",

                    # REQ string: The person's email address
                    "email": "jgaff@uchicago.edu",

                    # RCM string: The primary affiliation for the person
                    "institution": "The University of Chicago",

                    # RCM string: The person's GitHub username
                    "github": "jgaff",


                }],

                # RCM list of strings: The full bibliographic citation(s) for the dataset
#                "citation": ,

                # RCM list of dictionaries: A list of the authors of this dataset
                "author": [{

                    # REQ string: The person's given (or first) name
                    "given_name": "Andre",

                    # REQ string: The person's family (or last) name
                    "family_name": "Schleife",

                    # REQ string: The person's email address
                    "email": "schleife@illinois.edu",

                    # RCM string: The primary affiliation for the person
                    "institution": "University of Illinois Urbana-Champaign",


                }],

                # RCM string: A link to the license for distribution of the dataset
#                "license": ,

                # RCM string: The repository (that should already be in MDF) holding the dataset
#                "repository": ,

                # RCM string: The collection for the dataset, commonly a portion of the title
#                "collection": ,

                # RCM list of strings: Tags, keywords, or other general descriptors for the dataset
#                "tags": ,

                # RCM string: A description of the dataset
#                "description": ,

                # RCM integer: The year of dataset creation
#                "year": ,

                # REQ dictionary: Links relating to the dataset
                "links": {

                    # REQ string: The human-friendly landing page for the dataset
                    "landing_page": "https://www.globus.org/app/transfer?origin_id=e38ee745-6d04-11e5-ba46-22000b92c6ec&origin_path=%2FSchleife%2Fstopping_proton_si_001_channel%2F",

                    # RCM list of strings: The DOI(s) (in link form, ex. 'https://dx.doi.org/10.12345') for publications connected to the dataset
#                    "publication": ,

                    # RCM string: The DOI of the dataset itself (in link form)
#                    "data_doi": ,

                    # OPT list of strings: The mdf-id(s) of related entries, not including records from this dataset
#                    "related_id": ,

                    # RCM dictionary: Links to raw data files from the dataset (multiple allowed, field name should be data type)
                    "data_link": {

                        # RCM string: The ID of the Globus Endpoint hosting the file
                        "globus_endpoint": "e38ee745-6d04-11e5-ba46-22000b92c6ec",

                        # RCM string: The fully-qualified HTTP hostname, including protocol, but without the path (for example, 'https://data.materialsdatafacility.org')
#                        "http_host": "https://data.materialsdatafacility.org",

                        # REQ string: The full path to the data file on the host
                        "path": "/Schleife/stopping_proton_si_001_channel/",

                    },

                },

            },

            # OPT dictionary: DataCite-format metadata
            "dc": {

            },


        }
        ## End metadata
    elif type(metadata) is str:
        try:
            dataset_metadata = json.loads(metadata)
        except Exception:
            try:
                with open(metadata, 'r') as metadata_file:
                    dataset_metadata = json.load(metadata_file)
            except Exception as e:
                sys.exit("Error: Unable to read metadata: " + repr(e))
    elif type(metadata) is dict:
        dataset_metadata = metadata
    else:
        sys.exit("Error: Invalid metadata parameter")



    # Make a Validator to help write the feedstock
    # You must pass the metadata to the constructor
    # Each Validator instance can only be used for a single dataset
    # If the metadata is incorrect, the constructor will throw an exception and the program will exit
    dataset_validator = Validator(dataset_metadata)


    # Get the data
    #    Each record should be exactly one dictionary
    #    You must write your records using the Validator one at a time
    #    It is recommended that you use a parser to help with this process if one is available for your datatype
    #    Each record also needs its own metadata
    errors = []
    for file_data in tqdm(toolbox.find_files(input_path, "^((?!png).)*$"), desc="Processing files", disable= not verbose):
        # Preprocessing malformed files
        file_path = os.path.join(file_data["path"], file_data["filename"])
        if file_path.endswith("out") or file_path.endswith("cub") or file_path.endswith("cube"):
            with open(file_path, 'r') as f:
                f_data = f.read().replace(" expectation set", "_expectation_set").replace(" expectation values", "_expectation_values")
            with open(file_path, 'w') as f:
                f.write(f_data)
        try:
            record = parse_ase(file_path=file_path, data_format="qbox")
        except Exception as e:
            try:
                record = parse_ase(file_path=file_path, data_format="cube")
            except Exception as e:
                try:
                    record = parse_ase(file_path=file_path)
                except Exception as e:
                    # Many files will not be ASE-readable
                    errors.append(file_path)
                    continue
        # Fields can be:
        #    REQ (Required, must be present)
        #    RCM (Recommended, should be present if possible)
        #    OPT (Optional, can be present if useful)
        ## Metadata:record
        record_metadata = {
            # REQ dictionary: MDF-format record metadata
            "mdf": {

                # REQ string: The title of the record
                "title": "H Projectile in Si: Channel Trajectories - " + record["chemical_formula"],

                # RCM list of strings: The UUIDs allowed to view this metadata, or 'public' (defaults to the dataset ACL)
                "acl": ["public"],

                # RCM string: Subject material composition, expressed in a chemical formula (ex. Bi2S3)
                "composition": record["chemical_formula"],

                # RCM list of strings: Tags, keywords, or other general descriptors for the record
#                "tags": ,

                # RCM string: A description of the record
#                "description": ,

                # RCM string: The record as a JSON string (see json.dumps())
#                "raw": ,

                # REQ dictionary: Links relating to the record
                "links": {

                    # RCM string: The human-friendly landing page for the record (defaults to the dataset landing page)
#                    "landing_page": ,

                    # RCM list of strings: The DOI(s) (in link form, ex. 'https://dx.doi.org/10.12345') for publications specific to this record
#                    "publication": ,

                    # RCM string: The DOI of the record itself (in link form)
#                    "data_doi": ,

                    # OPT list of strings: The mdf-id(s) of related entries, not including the dataset entry
#                    "related_id": ,

                    # RCM dictionary: Links to raw data files from the dataset (multiple allowed, field name should be data type)
                    "file": {

                        # RCM string: The ID of the Globus Endpoint hosting the file
                        "globus_endpoint": "e38ee745-6d04-11e5-ba46-22000b92c6ec",

                        # RCM string: The fully-qualified HTTP hostname, including protocol, but without the path (for example, 'https://data.materialsdatafacility.org')
#                        "http_host": ,

                        # REQ string: The full path to the data file on the host
                        "path": os.path.join("/Schleife/", file_data["no_root_path"], file_data["filename"]),

                    },

                },

                # OPT list of strings: The full bibliographic citation(s) for the record, if different from the dataset
#                "citation": ,

                # OPT dictionary: The contact person/steward/custodian for the record, if different from the dataset
#                "data_contact": {

                    # REQ string: The person's given (or first) name
#                    "given_name": ,

                    # REQ string: The person's family (or last) name
#                    "family_name": ,

                    # REQ string: The person's email address
#                    "email": ,

                    # RCM string: The primary affiliation for the person
#                    "institution": ,

#                },

                # OPT list of dictionaries: A list of the authors of this record, if different from the dataset
#                "author": [{

                    # REQ string: The person's given (or first) name
#                    "given_name": ,

                    # REQ string: The person's family (or last) name
#                    "family_name": ,

                    # RCM string: The person's email address
#                    "email": ,

                    # RCM string: The primary affiliation for the person
#                    "institution": ,


#                }],

                # OPT integer: The year of dataset creation, if different from the dataset
#                "year": ,

            },

            # OPT dictionary: DataCite-format metadata
            "dc": {

            },


        }
        ## End metadata

        # Pass each individual record to the Validator
        result = dataset_validator.write_record(record_metadata)

        # Check if the Validator accepted the record, and stop processing if it didn't
        # If the Validator returns "success" == True, the record was written successfully
        if not result["success"]:
            if not dataset_validator.cancel_validation()["success"]:
                print("Error cancelling validation. The partial feedstock may not be removed.")
            raise ValueError(result["message"] + "\n" + result.get("details", ""))


    # You're done!
    if verbose:
        print("Finished converting")
        print("There were", len(errors), "errors.")
