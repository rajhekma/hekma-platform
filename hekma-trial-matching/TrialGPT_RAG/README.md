# Clinical Trial Matching Pipeline

A hybrid retrieval and LLM-based eligibility reasoning system for matching patients to relevant clinical trials.

---

## Overview

Given a free-text patient note, the pipeline:
1. Extracts a structured patient profile using an LLM
2. Retrieves candidate trials from a Qdrant vector database using hybrid search (dense + sparse)
3. Reasons over each trial's inclusion/exclusion criteria criterion-by-criterion using an LLM

---

## Architecture

```
Patient Note
     │
     ▼
extract_patient_profile()       ← LLM call 1: structured profile
expand_query_terms()            ← LLM call 2: BM25-optimized synonyms
     │
     ▼
Qdrant Hybrid Search (RRF Fusion)
  ├── Dense prefetch     (text-embedding-3-large)
  ├── Sparse prefetch 1  (BM25 from profile keywords)
  ├── Sparse prefetch 2  (BM25 from expanded terms)
  └── Sparse prefetch 3  (BM25 from raw patient note)
     │
     ▼
Top-K Candidate Trials
     │
     ▼
LLM Criterion Reasoning         ← GPT call per trial (inclusion + exclusion)
     │
     ▼
Eligibility Results (JSON)
```

---

## Stack

- **Vector DB**: Qdrant (hybrid dense + sparse)
- **Embeddings**: OpenAI `text-embedding-3-large` (3072-dim)
- **Sparse**: BM25 via `fastembed` (`Qdrant/bm25`)
- **LLM**: Configurable via `LLM_MODEL` in `config.py` (default: `gpt-5.4`)
- **Fusion**: Reciprocal Rank Fusion (RRF)

---

## Project Structure

| File | Purpose |
|------|---------|
| `config.py` | Clients, constants, LLM model, and prompts |
| `ingestion.py` | Parse corpus and upsert into Qdrant |
| `retrieval.py` | Hybrid retrieval with RRF fusion |
| `utils.py` | Embeddings, BM25, profile extraction, query expansion |
| `matching.py` | LLM criterion-level eligibility reasoning |
| `save_retrieve.py` | Batch retrieval over all queries, saves structured JSON |
| `benchmark_retrieval.py` | Evaluate retrieval with Recall, Precision, MAP, MRR |
| `main.py` | End-to-end entry point |

---

## Setup

```bash
pip install openai qdrant-client fastembed python-dotenv tqdm
```

Create a `.env` file:
```
OPENAI_API_KEY=your_key_here
```

Start Qdrant locally:
```bash
docker run -p 6333:6333 qdrant/qdrant
```

---

## Usage

### 1. Ingest corpus

```bash
python main.py --corpus corpus.jsonl
```

To drop and recreate the collection before ingesting:
```bash
python main.py --corpus corpus.jsonl --recreate
```

### 2. Query only (skip ingestion)

```bash
python main.py --no-ingest --patient "58-year-old female with chest pain..."
```

### 3. Batch retrieval

```bash
python save_retrieve.py -qu queries.jsonl -c corpus.jsonl --output retrieved.json --top-k 50 --threshold 0.1
```

### 4. LLM criterion reasoning

```bash
python matching.py -r retrieved.json --output reasoning.json
```

### 5. Benchmark retrieval

```bash
python benchmark_retrieval.py -qu queries.jsonl -qr qrels.tsv --top-k 50 -k 2 5 10 -t 0.1 -o results.json
```

---

## Configuration

All model and prompt configuration lives in `config.py`:

| Constant | Description |
|----------|-------------|
| `LLM_MODEL` | LLM used for profile extraction, query expansion, and matching |
| `COLLECTION` | Qdrant collection name |
| `DENSE_DIM` | Embedding dimension (3072 for `text-embedding-3-large`) |
| `PATIENT_EXTRACTION_PROMPT` | Prompt for structured profile extraction |
| `QUERY_EXPANSION_PROMPT` | Prompt for BM25 query term expansion |

---

## Benchmark Output

`benchmark_retrieval.py` prints and saves a JSON file with:

- **Summary**: MAP, MRR, mean Recall@K, mean Precision@K
- **Per-query**: retrieved IDs, relevant IDs, per-metric scores, elapsed time

---

## Input Formats

**corpus.jsonl** — one trial per line:
```json
{"_id": "NCT0001234", "title": "...", "metadata": {"brief_summary": "...", "inclusion_criteria": "...", "exclusion_criteria": "...", "diseases_list": [], "drugs_list": []}}
```

**queries.jsonl** — one patient per line:
```json
{"_id": "patient_001", "text": "58-year-old female with chest pain..."}
```

**qrels.tsv** — relevance judgements:
```
query_id	corpus_id	score
patient_001	NCT0001234	1
```
