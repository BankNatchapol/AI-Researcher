"""Community-attention discourse adapters — separate channel from evidence sources."""

from ai_researcher.discourse.hackernews import HackerNewsSource
from ai_researcher.discourse.reddit import RedditSource
from ai_researcher.discourse.registry import register

register(RedditSource())
register(HackerNewsSource())
