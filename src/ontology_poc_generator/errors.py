class ScenarioValidationError(ValueError):
    """Scenario parameters are incomplete or internally inconsistent."""


class KnowledgeValidationError(ValueError):
    """A knowledge unit violates the source-backed candidate contract."""
