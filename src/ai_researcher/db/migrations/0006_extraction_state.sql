CREATE TABLE paper_extraction_state (
    paper_id BIGINT PRIMARY KEY REFERENCES paper(id) ON DELETE CASCADE,
    extraction_model TEXT NOT NULL,
    prompt_version TEXT NOT NULL,
    completed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO paper_extraction_state (
    paper_id,
    extraction_model,
    prompt_version,
    completed_at
)
SELECT DISTINCT ON (paper_id)
    paper_id,
    extraction_model,
    prompt_version,
    created_at
FROM (
    SELECT paper_id, extraction_model, prompt_version, created_at FROM claim
    UNION ALL
    SELECT paper_id, extraction_model, prompt_version, created_at FROM method
    UNION ALL
    SELECT paper_id, extraction_model, prompt_version, created_at FROM result
    UNION ALL
    SELECT paper_id, extraction_model, prompt_version, created_at FROM dataset
    UNION ALL
    SELECT paper_id, extraction_model, prompt_version, created_at FROM metric
) AS existing_extractions
ORDER BY paper_id, created_at DESC;
