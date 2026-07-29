ALTER TABLE paper_extraction_state
    ADD COLUMN validation_accepted INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN validation_rejected INTEGER NOT NULL DEFAULT 0,
    ADD CONSTRAINT ck_paper_extraction_state_validation_accepted
        CHECK (validation_accepted >= 0),
    ADD CONSTRAINT ck_paper_extraction_state_validation_rejected
        CHECK (validation_rejected >= 0);
