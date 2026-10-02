"""
guardrails — NeMo-style safety rails for the RAG Workbench.

Phase 13: Input & Dialog Rails
  - input_rails:  prompt injection & jailbreak detection
  - dialog_rails: off-topic query detection

Phase 14: Retrieval & Execution Rails
  - retrieval_rails:  relevance filtering for retrieved chunks
  - execution_rails:  SQL/math execution safety

Phase 15: Output Rails
  - output_rails: hallucination detection & PII masking
"""

from api.services.guardrails.input_rails import check_input, InputVerdict
from api.services.guardrails.dialog_rails import check_dialog, DialogVerdict
from api.services.guardrails.retrieval_rails import filter_retrieval, RetrievalVerdict
from api.services.guardrails.execution_rails import check_execution, ExecutionVerdict
from api.services.guardrails.output_rails import check_output, OutputVerdict

__all__ = [
    "check_input", "InputVerdict",
    "check_dialog", "DialogVerdict",
    "filter_retrieval", "RetrievalVerdict",
    "check_execution", "ExecutionVerdict",
    "check_output", "OutputVerdict",
]
