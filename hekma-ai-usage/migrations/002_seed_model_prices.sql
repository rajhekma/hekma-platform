-- List prices current as of 2026-10. New rows with a later effective_from
-- supersede earlier ones; ingested events keep the cost they were given.

INSERT INTO ai_model_prices (provider, model, input_usd_per_1m, output_usd_per_1m, effective_from)
VALUES
    ('openai',    'gpt-4o',              2.500000, 10.000000, TIMESTAMPTZ '2024-08-01 00:00:00+00'),
    ('openai',    'gpt-4o-mini',         0.150000,  0.600000, TIMESTAMPTZ '2024-07-18 00:00:00+00'),
    ('openai',    'gpt-4.1',             2.000000,  8.000000, TIMESTAMPTZ '2025-04-14 00:00:00+00'),
    ('openai',    'gpt-4.1-mini',        0.400000,  1.600000, TIMESTAMPTZ '2025-04-14 00:00:00+00'),
    ('openai',    'gpt-4.1-nano',        0.100000,  0.400000, TIMESTAMPTZ '2025-04-14 00:00:00+00'),
    ('anthropic', 'claude-sonnet-4-6',   3.000000, 15.000000, TIMESTAMPTZ '2025-11-01 00:00:00+00'),
    ('anthropic', 'claude-sonnet-4-5',   3.000000, 15.000000, TIMESTAMPTZ '2025-09-01 00:00:00+00'),
    ('anthropic', 'claude-sonnet-4',     3.000000, 15.000000, TIMESTAMPTZ '2025-05-22 00:00:00+00'),
    ('anthropic', 'claude-3-5-sonnet',   3.000000, 15.000000, TIMESTAMPTZ '2024-06-20 00:00:00+00'),
    ('anthropic', 'claude-3-haiku',      0.250000,  1.250000, TIMESTAMPTZ '2024-03-13 00:00:00+00'),
    ('google',    'gemini-1.5-pro',      1.250000,  5.000000, TIMESTAMPTZ '2024-09-24 00:00:00+00'),
    ('google',    'gemini-1.5-flash',    0.075000,  0.300000, TIMESTAMPTZ '2024-09-24 00:00:00+00'),
    ('google',    'gemini-2.0-flash',    0.100000,  0.400000, TIMESTAMPTZ '2024-12-11 00:00:00+00'),
    ('google',    'gemini-2.5-pro',      1.250000, 10.000000, TIMESTAMPTZ '2025-03-25 00:00:00+00'),
    ('groq',      'llama-3.3-70b',       0.590000,  0.790000, TIMESTAMPTZ '2024-12-01 00:00:00+00'),
    ('groq',      'qwen',                0.200000,  0.200000, TIMESTAMPTZ '2025-06-01 00:00:00+00')
ON CONFLICT (provider, model, effective_from) DO NOTHING;
