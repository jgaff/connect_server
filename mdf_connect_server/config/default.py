import os


DEFAULT = {
    "LOCAL_PATH": os.path.expanduser("~/data/"),
    "FEEDSTOCK_PATH": os.path.expanduser("~/feedstock/"),
    "SERVICE_DATA": os.path.expanduser("~/integrations/"),

    "SCHEMA_PATH": os.path.abspath(os.path.join(os.path.dirname(__file__), "schemas")),

    "PROCESSOR_WAIT_TIME": 20,  # Seconds
    "PROCESSOR_SLEEP_TIME": 40,  # Seconds

    "CANCEL_WAIT_TIME": 60,  # 1 minute, in seconds

    "TRANSFER_PING_INTERVAL": 1 * 60,  # 1 minute, in seconds
    "TRANSFER_DEADLINE": 3 * 60 * 60,  # 3 hours, in seconds
    "TRANSFER_WEB_APP_LINK": "https://www.globus.org/app/transfer?origin_id={}&origin_path={}",

    "SEARCH_BATCH_SIZE": 100,

    "PUBLISH_COLLECTIONS": {
        "21": {
            "name": "MDF Open",
            "group": "1c562600-1083-11e6-846d-22000ab80e73"
        },
        "35": {
            "name": "MDF Test",
            "group": "115fb604-a2cb-11e7-a5d0-22000b500e8d"
        },
        "55": {
            "name": "NUCAPT",
            "group": "7ac7bef4-ba8e-11e7-9f15-22000b93c8ac"
        }
    },
    "PUBLISH_LINK": "https://publish.globus.org/jspui/handle/ITEM/{}",

    "CITRINATION_LINK": "https://citrination.com/datasets/{cit_ds_id}/",

    "MRR_URL": "https://mrr.materialsdatafacility.org/rest/curate",

    "MRR_SCHEMA": "5a79c146be2d440472d045d4",

    "API_CLIENT_ID": "c17f27bb-f200-486a-b785-2a25e82af505",
    "API_SCOPE": "https://auth.globus.org/scopes/c17f27bb-f200-486a-b785-2a25e82af505/connect",
    "API_SCOPE_ID": "mdf_dataset_submission",

    "GDRIVE_ROOT": "/Shared With Me",

    "ADMIN_GROUP_ID": "5fc63928-3752-11e8-9c6f-0e00fd09bf20",
    "CONVERT_GROUP_ID": "cc192dca-3751-11e8-90c1-0a7c735d220a",
    "INGEST_GROUP_ID": "3ce2c53e-3752-11e8-891c-0e00fd09bf20"
}
with open(os.path.join(DEFAULT["SCHEMA_PATH"], "mrr_template.xml")) as f:
    DEFAULT["MRR_TEMPLATE"] = f.read()
with open(os.path.join(DEFAULT["SCHEMA_PATH"], "mrr_contributor.xml")) as f:
    DEFAULT["MRR_CONTRIBUTOR"] = f.read()