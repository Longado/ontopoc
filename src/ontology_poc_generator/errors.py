class ScenarioValidationError(ValueError):
    """Scenario parameters are incomplete or internally inconsistent."""


class KnowledgeValidationError(ValueError):
    """A knowledge unit violates the source-backed candidate contract."""


class OntologySpecValidationError(ValueError):
    """A draft ontology spec violates its frozen local contract."""


class SpecCompilationError(ValueError):
    """A pack cannot be compiled into a trustworthy ontology spec."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
