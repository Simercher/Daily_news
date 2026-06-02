from dataclasses import dataclass

@dataclass
class Score:
    velocity_score: float = 0.0
    source_diversity_score: float = 0.0
    severity_score: float = 0.0
    final_score: float = 0.0

__all__ = ["Score"]
