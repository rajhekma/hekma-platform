# Event schemas

Async contracts for the event bus (LocalStack SQS in local dev, AWS SQS in production).

| Event | Producer | Consumers | Status |
|-------|----------|-----------|--------|
| `ai.usage.recorded` | Scan AI, EHR summary, TrialGPT | hekma-platform `hekma-ai-usage` | **Live** — [ai.usage.recorded.v1.json](./ai.usage.recorded.v1.json) |
| `scan.completed` | MS-11 Clinical Scanner | MS-08 Patient Profile, MS-10 FHIR | Planned |
| `ehr.ingested` | MS-09 EHR Integration | MS-13 Summary, MS-15 Trial Platform | Planned |
| `account.deleted` | MS-14 Account Compliance | MS-01 Auth, MS-03 Notification | Planned |
| `patient.enrolled` | MS-02 CTMS Core | MS-03 Notification | Planned |

Add JSON Schema files here as services are extracted (e.g. `scan.completed.v1.json`).
