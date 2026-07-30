"""Community-attention discourse adapters — separate channel from evidence sources."""

from ai_researcher.discourse.hackernews import HackerNewsSource
from ai_researcher.discourse.huggingface import HuggingFacePapersSource
from ai_researcher.discourse.reddit import RedditSource
from ai_researcher.discourse.registry import register
from ai_researcher.discourse.rss_blogs import RssBlogsSource

register(RedditSource())
register(HackerNewsSource())
register(RssBlogsSource())
register(HuggingFacePapersSource())
