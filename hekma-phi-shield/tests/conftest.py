import os
import pytest

# Ensure unit tests run with local fast JSON/Memory storage by default
os.environ["STORAGE_BACKEND"] = "json"
