import os, json

def load_json(path, default=None):
    if not os.path.exists(path):
        return default
    with open(path) as f:
        return json.load(f)

def load_jsonl(path):
    with open(path) as f:
        return [json.loads(line) for line in f]
