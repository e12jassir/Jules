from collections import deque
from collections.abc import Sequence
import logging
import re
import statistics
from typing import Protocol

from jules.memory.models import Episode

DEFAULT_IMPORTANCE_SCORE = 0.5
SCORE_PATTERN = r"SCORE:\s*(0\.\d+|1\.0|0|1)(?![\w.])"


class TextGenerationProvider(Protocol):
    async def generate_text(self, prompt: str) -> str: ...


class ScoringHealthMonitor:
    def __init__(self, scoring_variance_threshold: float = 0.01, scoring_window_size: int = 10) -> None:
        if scoring_variance_threshold < 0:
            raise ValueError("scoring_variance_threshold must be >= 0")
        if scoring_window_size < 3:
            raise ValueError("scoring_window_size must be >= 3")
        self.scoring_variance_threshold = scoring_variance_threshold
        self._scores: deque[float] = deque(maxlen=scoring_window_size)

    @property
    def scores(self) -> Sequence[float]:
        return tuple(self._scores)

    def record(self, score: float) -> None:
        self._scores.append(score)

    def is_healthy(self) -> bool:
        if len(self._scores) < 3:
            return True
        return statistics.variance(self._scores) > self.scoring_variance_threshold


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
        matches = re.findall(SCORE_PATTERN, response, re.IGNORECASE)
        if matches:
            return float(matches[-1])
        logging.warning("Scoring fallback: could not parse score from provider response")
    except Exception as error:
        logging.error("Scoring fallback: provider evaluation failed: %s", error)
    return DEFAULT_IMPORTANCE_SCORE
