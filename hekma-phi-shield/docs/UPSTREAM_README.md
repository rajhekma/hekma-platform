# PHI-PII Detection Service

Fine-tuned RoBERTa model for detecting personally identifiable information (PII) in text, with a REST API and browser-based validation UI.

## Project structure

```
PHI-PII/
├── api/                        # FastAPI service + web UI
│   ├── main.py
│   └── ui/
├── models/
│   └── roberta-pii-synthetic/  # Trained model (with weights)
├── training/
│   ├── notebooks/              # Fine-tuning pipeline
│   ├── data/                   # Training dataset
│   └── artifacts/              # Checkpoints (gitignored)
├── tests/
│   └── test_api.py
├── requirements.txt
└── README.md
```

## Quick start

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python api/main.py
```

- **UI:** http://localhost:8080/
- **API docs:** http://localhost:8080/docs

## API endpoints

| Endpoint | Description |
|---|---|
| `POST /predict` | Detect PII in text |
| `POST /predict/batch` | Batch detection (up to 50 texts) |
| `POST /validate` | Compliance check — does text contain PII? |
| `POST /mask` | Redact detected PII |
| `GET /health` | Model status |
| `GET /entities` | List supported entity types |

## Model weights

The fine-tuned model weights are included in the repository at:

```
models/roberta-pii-synthetic/model.safetensors
```

No additional setup needed — the model is ready to use after cloning.

## Training

To retrain the model with your own data:

1. Open `training/notebooks/fine_tune_pipeline.ipynb`
2. Dataset is at `training/data/synthetic_dataset.json`
3. Fine-tuned model saves to `models/roberta-pii-synthetic/`
4. Checkpoints go to `training/artifacts/results/` (gitignored)

## Testing

```powershell
python tests/test_api.py
```
