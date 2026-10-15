import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv

load_dotenv()

from utils.qdrant_util import get_qdrant_client

collection = os.getenv("QDRANT_PATIENT_COLLECTION", "patient_profiles_hybrid_v1")
client = get_qdrant_client()
try:
    info = client.count(collection_name=collection, exact=True)
    print("collection:", collection)
    print("points:", info.count)
except Exception as exc:
    print("error:", exc)
