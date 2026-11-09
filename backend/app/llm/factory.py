import os

from .heuristic import HeuristicProvider


def get_provider():
    """LLM_PROVIDER selects the AI setup: anthropic (Messages API) or the offline heuristic provider (default)."""
    provider = os.environ.get("LLM_PROVIDER", "heuristic")
    if provider == "anthropic":
        from .anthropic_provider import AnthropicProvider

        return AnthropicProvider()
    return HeuristicProvider()
