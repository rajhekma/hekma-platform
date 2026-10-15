"""
Resumable, chunked Qdrant embed for all ready trialgpt_eligible_patients.

- Embedding model: text-embedding-3-large (dense, 3072-dim) + local BM25 sparse.
- Idempotent: Qdrant points use a stable id per subject_id, so re-running is safe.
- Resumable: a progress file tracks the next offset, so a restart never re-pays
  OpenAI cost for chunks already completed.

Usage:
  python scripts/run_patient_embed.py                 # full run
  python scripts/run_patient_embed.py --limit 2       # smoke test (first 2)
  python scripts/run_patient_embed.py --chunk-size 1000
  python scripts/run_patient_embed.py --reset         # start progress over
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv()

from services.patient_qdrant_embed_service import (
    DEFAULT_EMBED_ERROR_PATH,
    _fetch_all_compose_patient_ids,
    embed_patient_ids,
)

DEFAULT_PROGRESS_PATH = ROOT / "results" / "patient_embed_progress.json"


def _load_progress(path: Path) -> dict:
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"next_offset": 0, "upserted": 0, "failed": 0, "failed_offsets": []}


def _save_progress(path: Path, progress: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(progress, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser(description="Chunked resumable patient Qdrant embed.")
    parser.add_argument("--chunk-size", type=int, default=1000, help="Patients per subprocess chunk.")
    parser.add_argument("--batch-size", type=int, default=50, help="Qdrant upsert batch size.")
    parser.add_argument("--limit", type=int, default=0, help="Only embed the first N ready patients (smoke test).")
    parser.add_argument("--reset", action="store_true", help="Reset progress and start from offset 0.")
    parser.add_argument("--progress-path", default=str(DEFAULT_PROGRESS_PATH))
    parser.add_argument("--error-path", default=str(DEFAULT_EMBED_ERROR_PATH))
    args = parser.parse_args()

    progress_path = Path(args.progress_path)
    error_path = Path(args.error_path)

    ids = _fetch_all_compose_patient_ids(limit=args.limit if args.limit > 0 else None)
    total = len(ids)
    print(f"[embed] ready_patients={total} chunk_size={args.chunk_size}", flush=True)
    if total == 0:
        print("[embed] nothing to embed")
        return 0

    progress = {"next_offset": 0, "upserted": 0, "failed": 0, "failed_offsets": []}
    if not args.reset:
        progress = _load_progress(progress_path)
    # A smaller cohort (smoke/limit) should not inherit a huge saved offset.
    if progress.get("next_offset", 0) > total:
        progress["next_offset"] = 0

    start = time.time()
    offset = int(progress.get("next_offset", 0))

    while offset < total:
        chunk = ids[offset : offset + args.chunk_size]
        chunk_end = offset + len(chunk)
        t0 = time.time()

        stats = None
        last_err = None
        for attempt in range(1, 4):
            try:
                stats = embed_patient_ids(
                    chunk,
                    batch_size=args.batch_size,
                    recreate=False,
                    error_path=error_path,
                )
                break
            except Exception as exc:  # transient DB / API / network hiccup
                last_err = exc
                print(
                    f"[embed] chunk {offset}-{chunk_end} attempt {attempt} failed: {exc}; retrying...",
                    flush=True,
                )
                time.sleep(min(30, 5 * attempt))

        if stats is None:
            # All retries exhausted: record the range and continue (idempotent rerun can recover).
            print(
                f"[embed] chunk {offset}-{chunk_end} permanently failed after retries: {last_err}",
                flush=True,
            )
            stats = {"upserted": 0, "failed": len(chunk)}

        dt = time.time() - t0

        progress["upserted"] = int(progress.get("upserted", 0)) + int(stats.get("upserted", 0))
        progress["failed"] = int(progress.get("failed", 0)) + int(stats.get("failed", 0))
        if stats.get("failed", 0):
            progress.setdefault("failed_offsets", []).append([offset, chunk_end])

        offset = chunk_end
        progress["next_offset"] = offset
        _save_progress(progress_path, progress)

        done = progress["upserted"] + progress["failed"]
        rate = done / max(1e-6, (time.time() - start))
        eta_min = (total - offset) / max(1e-6, rate) / 60.0
        print(
            f"[embed] progress {offset}/{total} "
            f"(chunk upserted={stats.get('upserted', 0)} failed={stats.get('failed', 0)} "
            f"in {dt:.1f}s) total_upserted={progress['upserted']} total_failed={progress['failed']} "
            f"eta_min={eta_min:.1f}",
            flush=True,
        )

    print(
        json.dumps(
            {
                "done": True,
                "total": total,
                "upserted": progress["upserted"],
                "failed": progress["failed"],
                "failed_offsets": progress.get("failed_offsets", []),
                "elapsed_min": round((time.time() - start) / 60.0, 2),
                "progress_path": str(progress_path),
                "error_path": str(error_path),
            },
            indent=2,
        ),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
