# Provenance

Copied from `hekma_data_pipeline/hekma_data_pipleline` on 11 Oct 2026.
The monolith was not modified.

Product surfaces copied:

- MS-11 Clinical Scanner (`apis/clinical_scans_api.py`, `services/clinical_scans/`)
- MS-13 EHR Summary (`apis/ehr_summary_api.py`, `fasten_health/ehr_summary_*`)

Shared helpers (auth, Postgres, FHIR store write, privacy client, AI usage
emitter) were taken from the already-stripped `hekma-patient-health` tree so
this service does not reintroduce cloud keys.

Medication *APIs* were not copied. `services/medications/` persist helpers
remain because `persistRecords=true` still writes extracted medicines during
the strangler period.
