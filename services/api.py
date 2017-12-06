from hashlib import sha512
import json
import os
import re
import shutil
import tempfile
from threading import Thread
import zipfile

from bson import ObjectId
from citrination_client import CitrinationClient
from flask import jsonify, request
import magic
from mdf_toolbox import toolbox
from mdf_refinery import ingester, omniparser, validator
from pif_ingestor.manager import IngesterManager
from pypif.pif import dump as pif_dump
from pypif_sdk.util import citrination as cit_utils
from pypif_sdk.interop.mdf import _to_user_defined as pif_to_feedstock
from pypif_sdk.interop.datacite import add_datacite as add_dc

import requests
from werkzeug.utils import secure_filename

from services import app

KEY_FILES = {
    "dft": {
        "exact": [],
        "extension": [],
        "regex": ["OUTCAR"]
    }
}


@app.route('/convert', methods=["POST"])
def accept_convert():
    """Accept the JSON metadata and begin the conversion process."""
    metadata = request.get_json(force=True, silent=True)
    if not metadata:
        return jsonify({
            "success": False,
            "error": "POST data empty or not JSON"
            })
    status_id = str(ObjectId())
    # TODO: Register status ID
    print("DEBUG: Status ID created")
    metadata["mdf_status_id"] = status_id
    converter = Thread(target=begin_convert, name="converter_thread", args=(metadata, status_id))
    converter.start()
    return jsonify({
        "success": True,
        "status_id": status_id
        })


def begin_convert(metadata, status_id):
    """Pull, back up, and convert metadata."""
    # Setup
    creds = {
        "app_name": "MDF Open Connect",
        "client_id": app.config["API_CLIENT_ID"],
        "client_secret": app.config["API_CLIENT_SECRET"],
        "services": ["transfer"]  # , "publish"]
        }
    clients = toolbox.confidential_login(creds)
    mdf_transfer_client = clients["transfer"]
#    globus_publish_client = clients["publish"]

    status_id = metadata["mdf_status_id"]

    # Download data locally, back up on MDF resources
    dl_res = download_and_backup(mdf_transfer_client, metadata)
    if dl_res["success"]:
        local_path = dl_res["local_path"]
        backup_path = dl_res["backup_path"]
    else:
        raise IOError("No data downloaded")
    # TODO: Update status - data downloaded
    print("DEBUG: Data downloaded")

    print("DEBUG: Conversions started")
    # TODO: Parse out dataset entry
    mdf_dataset = metadata

    # TODO: Stream data into files instead of holding feedstock in memory
    feedstock = [mdf_dataset]

    # TODO: Parse tags
    tags = []
    key_info = get_key_matches(tags or None)

    # List of all files, for bag
    all_files = []

    # Citrination setup
    cit_manager = IngesterManager()
    cit_client = CitrinationClient(app.config["CITRINATION_API_KEY"])
    # Get title and description
    try:
        cit_title = mdf_dataset["dc"]["titles"][0]["title"]
    except (KeyError, IndexError):
        cit_title = "Untitled"
    try:
        cit_desc = " ".join([desc["description"]
                            for desc in mdf_dataset["dc"]["descriptions"]])
        if not cit_desc:
            raise KeyError
    except (KeyError, IndexError):
        cit_desc = None
    cit_ds = cit_client.create_data_set(name=cit_title,
                                        description=cit_desc,
                                        share=0).json()
    cit_ds_id = cit_ds["id"]
    print("DEBUG: Citrine dataset ID:", cit_ds_id)

    for path, dirs, files in os.walk(os.path.abspath(local_path)):
        # Determine if dir or file is single entity
        # Dir is record
        if count_key_files(files, key_info) == 1:
            dir_file_md = []
            mdf_record = {}
            cit_res = {}
            # Process all files into one record
            for filename in files:
                # Get file metadata
                file_md = get_file_metadata(file_path=os.path.join(path, filename),
                                            backup_path=os.path.join(backup_path, path, filename))
                # Save file metadata
                all_files.append(file_md)
                dir_file_md.append(file_md)
                with open(os.path.join(path, filename)) as data_file:
                    # MDF parsing
                    mdf_res = omniparser.omniparse(data_file)
                    data_file.seek(0)

                    mdf_record = toolbox.dict_merge(mdf_record, mdf_res)

            # Citrine parsing
            print("DEBUG: path:", path)
            cit_pifs = cit_manager.run_extensions([os.path.abspath(path)],
                                                  include=None, exclude=[],
                                                  args={"quality_report": False})
            if not isinstance(cit_pifs, list):
                cit_pifs = [cit_pifs]
            # Continue processing only if PIF was extracted
            cit_full = []
            if len(cit_pifs) > 0:
                # Add UIDs to PIFs
                cit_pifs = cit_utils.set_uids(cit_pifs)
                for pif in cit_pifs:
                    # Get PIF URL
                    pif_land_page = {
                                        "mdf": {
                                            "landing_page": cit_utils.get_url(pif, cit_ds_id)
                                        }
                                    }
                    # Get MDF feedstock from PIFs and add PIF URL
                    cit_feed = toolbox.dict_merge(pif_to_feedstock(pif), pif_land_page)
                    cit_res = toolbox.dict_merge(cit_res, cit_feed)
                    # Add DataCite metadata to PIFs
                    pif = add_dc(pif, mdf_dataset["dc"])

                    cit_full.append(pif)

            else:
                # TODO: Send failed filetype to Citrine
                pass

            # Merge results
            mdf_record = toolbox.dict_merge(mdf_record, cit_res)

            # If data was parsed, save record
            if mdf_record:
                mdf_record = toolbox.dict_merge(mdf_record,
                                                {"files": dir_file_md})
                feedstock.append(mdf_record)

                for one_pif in cit_full:
                    with tempfile.NamedTemporaryFile(mode="w+") as pif_file:
                        pif_dump(one_pif, pif_file)
                        pif_file.seek(0)
                        up_res = json.loads(cit_client.upload(cit_ds_id, pif_file.name))
                        if up_res["success"]:
                            print("DEBUG: Citrine upload success")
                        else:
                            print("DEBUG: Citrine upload failure, error", up_res.get("status"))

        # File is record
        else:
            for filename in files:
                # Get file metadata
                file_md = get_file_metadata(file_path=os.path.join(path, filename),
                                            backup_path=os.path.join(backup_path, path, filename))
                with open(os.path.join(path, filename)) as data_file:
                    # MDF parsing
                    mdf_record = omniparser.omniparse(data_file)
                    data_file.seek(0)

                # Citrine parsing
                print("DEBUG: path:", path)
                cit_pifs = cit_manager.run_extensions([os.path.abspath(path)],
                                                      include=None, exclude=[],
                                                      args={"quality_report": False})
                if not isinstance(cit_pifs, list):
                    cit_pifs = [cit_pifs]
                # Continue processing only if PIF was extracted
                cit_full = []
                if len(cit_pifs) > 0:
                    # Add UIDs to PIFs
                    cit_pifs = cit_utils.set_uids(cit_pifs)
                    for pif in cit_pifs:
                        # Get PIF URL
                        pif_land_page = {
                                            "mdf": {
                                                "landing_page": cit_utils.get_url(pif, cit_ds_id)
                                            }
                                        }
                        # Get MDF feedstock from PIFs and add PIF URL
                        cit_res = toolbox.dict_merge(pif_to_feedstock(pif), pif_land_page)
                        # Add DataCite metadata to PIFs
                        pif = add_dc(pif, mdf_dataset["dc"])

                        cit_full.append(pif)

                else:
                    # TODO: Send failed filetype to Citrine
                    pass

                # Merge results
                mdf_record = toolbox.dict_merge(mdf_record, cit_res)

                # If data was parsed, save record
                if mdf_record:
                    mdf_record = toolbox.dict_merge(mdf_record,
                                                    {"files": dir_file_md})
                    feedstock.append(mdf_record)

                    for one_pif in cit_full:
                        with tempfile.NamedTemporaryFile(mode="w+") as pif_file:
                            pif_dump(one_pif, pif_file)
                            pif_file.seek(0)
                            up_res = json.loads(cit_client.upload(cit_ds_id, pif_file.name))
                            if up_res["success"]:
                                print("DEBUG: Citrine upload success")
                            else:
                                print("DEBUG: Citrine upload failure, error", up_res.get("status"))

    # TODO: Update status - indexing success
    print("DEBUG: Indexing success")

    # Pass feedstock to /ingest
    with tempfile.TemporaryFile(mode="w+") as stock:
        for entry in feedstock:
            json.dump(entry, stock)
            stock.write("\n")
        stock.seek(0)
        ingest_res = requests.post(app.config["INGEST_URL"],
                                   data={"status_id": status_id},
                                   files={'file': stock})
    if not ingest_res.json().get("success"):
        # TODO: Update status? Ingest failed
        # TODO: Fail everything, delete Citrine dataset, etc.
        raise ValueError("In convert - Ingest failed" + str(ingest_res.json()))

    # Finalize Citrine dataset
    # TODO: Turn on public dataset ingest
    # cit_client.update_data_set(cit_ds_id, share=1)

    # Pass data to additional integrations

    # Globus Publish
    # TODO: Enable after Publish API is fixed
    if False:  # metadata.get("globus_publish"):
        # Submit metadata
        try:
            pub_md = metadata["globus_publish"]
            md_result = globus_publish_client.push_metadata(pub_md["collection"], pub_md)
            pub_endpoint = md_result['globus.shared_endpoint.name']
            pub_path = os.path.join(md_result['globus.shared_endpoint.path'], "data") + "/"
            submission_id = md_result["id"]
        except Exception as e:
            # TODO: Update status - not Published due to bad metadata
            raise
        # Transfer data
        try:
            toolbox.quick_transfer(mdf_transfer_client, app.config["LOCAL_EP"],
                                   pub_endpoint, [(local_path, pub_path)], timeout=0)
        except Exception as e:
            # TODO: Update status - not Published due to failed Transfer
            raise
        # Complete submission
        try:
            fin_res = globus_publish_client.complete_submission(submission_id)
        except Exception as e:
            # TODO: Update status - not Published due to Publish error
            raise
        # TODO: Update status - Publish success
        print("DEBUG: Publish success")

    # Remove local data
    shutil.rmtree(local_path)
    return {
        "success": True,
        "status_id": status_id
        }


def download_and_backup(mdf_transfer_client, metadata):
    """Download remote data, backup"""
    status_id = metadata["mdf_status_id"]
    local_success = False
    local_path = os.path.join(app.config["LOCAL_PATH"], status_id) + "/"
    backup_path = os.path.join(app.config["BACKUP_PATH"], status_id) + "/"
    os.makedirs(local_path, exist_ok=True)  # TODO: exist not okay when status is real

    # Download data locally
    if metadata.get("zip"):
        # Download and unzip
        zip_path = os.path.join(local_path, metadata["mdf_status_id"] + ".zip")
        res = requests.get(metadata["zip"])
        with open(zip_path, 'wb') as out:
            out.write(res.content)
        zipfile.ZipFile(zip_path).extractall()  # local_path)
        os.remove(zip_path)  # TODO: Should the .zip be removed?
        local_success = True

    elif metadata.get("globus"):
        # Parse out EP and path
        # Right now, path assumed to be a directory
        user_ep, user_path = metadata["globus"].split("/", 1)
        user_path = "/" + user_path + ("/" if not user_path.endswith("/") else "")
        # Transfer locally
        toolbox.quick_transfer(mdf_transfer_client, user_ep, app.config["LOCAL_EP"],
                               [(user_path, local_path)], timeout=0)
        local_success = True

    elif metadata.get("files"):
        # TODO: Implement this
        pass

    else:
        # Nothing to do
        pass

    # TODO: Update status - download success/failure
    if not local_success:
        raise IOError("No data downloaded")
    print("DEBUG: Download success")

    # Backup data
    toolbox.quick_transfer(mdf_transfer_client,
                           app.config["LOCAL_EP"], app.config["BACKUP_EP"],
                           [(local_path, backup_path)], timeout=0)
    # TODO: Update status - backup success
    print("DEBUG: Backup success")

    return {
        "success": True,
        "local_path": local_path,
        "backup_path": backup_path
        }


def get_key_matches(tags=None):
    exa = []
    ext = []
    rex = []
    for tag, val in KEY_FILES.items():
        if not tags or tag in tags:
            for key in val.get("exact", []):
                exa.append(key.lower())
            for key in val.get("extension", []):
                ext.append(key.lower())
            for key in val.get("regex", []):
                rex.append(re.compile(key))
    return {
        "exact_keys": exa,
        "extension_keys": ext,
        "regex_keys": rex
    }


def count_key_files(files, key_info):
    return len([f for f in files
                if (f.lower() in key_info["exact_keys"]
                    or any([f.lower().endswith(ext) for ext in key_info["extension_keys"]])
                    or any([rx.match(f) for rx in key_info["regex_keys"]]))])


def get_file_metadata(file_path, backup_path):
    with open(file_path, "rb") as f:
        md = {
            "globus_endpoint": app.config["BACKUP_EP"] + backup_path,
            "data_type": magic.from_file(file_path),
            "mime_type": magic.from_file(file_path, mime=True),
            "url": app.config["BACKUP_HOST"] + backup_path,
            "length": os.path.getsize(file_path),
            "filename": os.path.basename(file_path),
            "sha512": sha512(f.read()).hexdigest()
        }
    return md


@app.route("/ingest", methods=["POST"])
def accept_ingest():
    """Accept the JSON feedstock file and begin the ingestion process."""
    # Check that file exists and is valid
    try:
        feedstock = request.files["file"]
    except KeyError:
        return jsonify({
            "success": False,
            "error": "No feedstock file uploaded"
            })
    # Mint/update status ID
    if not request.form.get("mdf_status_id"):
        status_id = str(ObjectId())
        # TODO: Register status ID
        print("DEBUG: New status ID created")
    else:
        # TODO: Check that status exists (must not be set by user)
        # TODO: Update status - ingest request recieved
        status_id = request.form.get("mdf_status_id")
        print("DEBUG: Current status ID read")
    # Save file
    feed_path = os.path.join(app.config["FEEDSTOCK_PATH"], secure_filename(feedstock.filename))
    feedstock.save(feed_path)
    ingester = Thread(target=begin_ingest, name="ingester_thread", args=(feed_path, status_id))
    ingester.start()
    return jsonify({
        "success": True,
        "status_id": status_id
        })


def begin_ingest(base_stock_path, status_id):
    """Finalize and ingest feedstock."""
    # Will need client to ingest data
    creds = {
        "app_name": "MDF Open Connect",
        "client_id": app.config["API_CLIENT_ID"],
        "client_secret": app.config["API_CLIENT_SECRET"],
        "services": ["search_ingest"],
        "index": app.config["INGEST_INDEX"]
        }
    search_client = toolbox.confidential_login(creds)["search_ingest"]
    final_feed_path = os.path.join(app.config["FEEDSTOCK_PATH"], status_id + "_final.json")

    # Validate feedstock
    val = validator.Validator()
    with open(base_stock_path, "r") as base_stock:
        # Validate dataset entry
        ds_res = val.start_dataset(json.loads(next(base_stock)))
        if not ds_res["success"]:
           # TODO: Update status - dataset validation failed
            raise Exception("ERROR:" + str(ds_res))

        # Validate records
        for rc in base_stock:
            record = json.loads(rc)
            rc_res = val.add_record(record)
            if not rc_res["success"]:
               # TODO: Update status - record validation failed
                raise Exception("ERROR:" + str(rc_res))
    os.remove(base_stock_path)

    # TODO: Update status - validation passed
    print("DEBUG: Validation success")
    # Write out feedstock
    with open(final_feed_path, 'w') as final_stock:
        for entry in val.get_finished_dataset():
            json.dump(entry, final_stock)
            final_stock.write("\n")

    # Ingest finalized feedstock
    try:
        ingester.ingest(search_client, final_feed_path)
    except Exception as e:
        # TODO: Update status - ingest failed
        raise Exception("ERROR:" + str({
            "success": False,
            "error": repr(e)
            }))
    # TODO: Update status - ingest successful, processing complete
    print("DEBUG: Ingest success, processing complete")
    return {
        "success": True,
        "status_id": status_id
        }


@app.route("/status", methods=["GET", "POST"])
def status():
    return jsonify({"success": False, "message": "Not implemented yet, try again later"})
