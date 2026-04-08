"""Abstract base class for all ai-radar source connectors.

Defines the Source interface that every connector must implement. This is
the type contract that makes RSS, HN, ArXiv, and Gmail connectors
interchangeable in the pipeline.

Stage: base interface — not a pipeline stage itself; imported by all connectors.
Input:  N/A
Output: N/A — defines the contract; concrete subclasses produce list[RawItem]

Spec reference: SPEC.md §3.1 (Source interface).
"""

# Standard library imports
from abc import ABC, abstractmethod

# Internal imports
from radar.models import RawItem


class Source(ABC):
    """Abstract base class for all source connectors.

    Subclasses must implement fetch(). Python's ABCMeta enforces this at
    subclass instantiation time — a subclass missing fetch() raises TypeError
    when instantiated, not when fetch() is called.
    """

    @abstractmethod
    def fetch(self) -> list[RawItem]: ...
