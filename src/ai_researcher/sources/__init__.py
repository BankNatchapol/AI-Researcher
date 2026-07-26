"""Built-in scholarly evidence-source adapters."""

from ai_researcher.sources.arxiv import ArxivSource
from ai_researcher.sources.openalex import OpenAlexSource
from ai_researcher.sources.registry import register
from ai_researcher.sources.semantic_scholar import SemanticScholarSource

register(ArxivSource())
register(OpenAlexSource())
register(SemanticScholarSource())
