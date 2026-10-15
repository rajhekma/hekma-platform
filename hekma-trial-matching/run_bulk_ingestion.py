import requests
import os

API_URL = "http://localhost:8000/api/trials/ingest"

for file in sorted(os.listdir()):
    if file.startswith("batch_") and file.endswith(".txt"):

        payload = {
            "type": "bulk_file",
            "file_path": file
        }

        print(f"Running ingestion for {file}")

        r = requests.post(API_URL, json=payload)

        print(r.json())