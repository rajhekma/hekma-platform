CREATE TABLE clinical_trials (
    nct_id TEXT PRIMARY KEY,          -- _id

    sponsor TEXT,
    eligibility_criteria TEXT,

    has_pir BOOLEAN NOT NULL DEFAULT FALSE,

    refined_criteria JSONB,            -- inclusion/exclusion
    protocol_section JSONB NOT NULL,   -- FullStudy.Study.ProtocolSection
    raw_resource JSONB NOT NULL,       -- FullStudy (entire doc)

    created_at TIMESTAMP DEFAULT now(),
    updated_at TIMESTAMP DEFAULT now()
);


CREATE INDEX idx_ct_nctid_sort
ON clinical_trials (nct_id ASC);

CREATE INDEX idx_ct_sponsor_fts
ON clinical_trials
USING GIN (to_tsvector('english', COALESCE(sponsor, '')));

CREATE INDEX idx_ct_criteria_fts
ON clinical_trials
USING GIN (to_tsvector('english', COALESCE(eligibility_criteria, '')));

CREATE INDEX idx_ct_has_pir
ON clinical_trials (has_pir);
