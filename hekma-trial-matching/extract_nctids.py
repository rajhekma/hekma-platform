import json
import sys
import os


def extract_nctids(input_json_file, output_txt_file="nct_ids.txt"):

    if not os.path.exists(input_json_file):
        print(f"File not found: {input_json_file}")
        return

    with open(input_json_file, "r") as f:
        data = json.load(f)

    nct_ids = []

    for item in data:
        try:
            nct_id = item["protocolSection"]["identificationModule"]["nctId"]
            nct_ids.append(nct_id)
        except KeyError:
            continue

    with open(output_txt_file, "w") as f:
        for nct in nct_ids:
            f.write(nct + "\n")

    print(f"{len(nct_ids)} NCT IDs written to {output_txt_file}")


if __name__ == "__main__":

    if len(sys.argv) < 2:
        print("Usage: python extract_nctids.py <path_to_json>")
        sys.exit(1)

    input_json_path = sys.argv[1]

    extract_nctids(input_json_path)