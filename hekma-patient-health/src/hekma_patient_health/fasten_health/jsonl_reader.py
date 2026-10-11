import json

def read_jsonl(file_text: str):
    for line in file_text.splitlines():
        line = line.strip()
        if line:
            yield json.loads(line)
