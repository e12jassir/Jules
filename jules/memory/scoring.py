import logging
import re
from typing import Protocol

from jules.memory.models import Episode

DEFAULT_IMPORTANCE_SCORE = 0.5
SCORE_PATTERN = r"SCORE:\s*(0\.\d+|1\.0|0|1)(?![\w.])"


class TextGenerationProvider(Protocol):
    async def generate_text(self, prompt: str) -> str: ...


def _build_prompt(episode: Episode) -> str:
    return (
        "Rate the technical importance of this memory episode from 0.0 to 1.0. "
        "Consider how important the problem and solution would be for future debugging, learning, or reuse.\n\n"
        f"Problem: {episode.problem or 'None'}\n"
        f"Solution: {episode.solution or 'None'}\n\n"
        "MUST END YOUR RESPONSE EXACTLY WITH 'SCORE: X.X'"
    )


async def evaluate_importance(episode: Episode, provider: TextGenerationProvider) -> float:
    try:
        response = await provider.generate_text(_build_prompt(episode))
        match = re.search(SCORE_PATTERN, response, re.IGNORECASE)
        if match:
            return float(match.group(1))
        logging.warning("Scoring fallback: could not parse score from provider response")
    except Exception as error:
        logging.warning("Scoring fallback: provider evaluation failed: %s", error)
    return DEFAULT_IMPORTANCE_SCORE
