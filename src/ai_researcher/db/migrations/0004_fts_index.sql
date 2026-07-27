CREATE INDEX ix_paper_search_document
    ON paper USING GIN (
        to_tsvector('english', coalesce(title, '') || ' ' || coalesce(abstract, ''))
    );

CREATE INDEX ix_section_search_document
    ON section USING GIN (to_tsvector('english', body_text));
