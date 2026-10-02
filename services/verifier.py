"""
verifier.py — Numeric and Semantic Entailment Verification logic.

This service implements the verification layer as described in the Prompt Plan.
It provides numeric cross-check with tolerance and NLI-based entailment verification.
"""
from typing import Tuple

from loguru import logger
try:
    from sentence_transformers import CrossEncoder
except ImportError:
    CrossEncoder = None


class Verifier:
    def __init__(self, model_name: str = "cross-encoder/nli-deberta-v3-small"):
        self.model = None
        self.model_name = model_name
        self.failed_to_load = False
        if CrossEncoder:
            try:
                self.model = CrossEncoder(model_name)
            except Exception as e:
                logger.error(f"Failed to load CrossEncoder model {model_name}: {e}")
                self.failed_to_load = True

    def verify_numeric(self, llm_value: float, xbrl_fact_value: float, tolerance: float = 0.005) -> bool:
        """
        Verify if the LLM-extracted numeric value matches the XBRL fact within a tolerance.
        Default tolerance is 0.5% (0.005).
        """
        if xbrl_fact_value == 0:
            return llm_value == 0
        
        diff = abs(llm_value - xbrl_fact_value)
        relative_diff = diff / abs(xbrl_fact_value)
        
        return relative_diff <= tolerance

    def verify_entailment(self, claim: str, source_text: str) -> Tuple[str, str]:
        """
        Verify if the source text strictly entails the generated claim using an NLI model.
        Returns a tuple of (PASS/FAIL/SKIPPED, reasoning).
        """
        if self.failed_to_load:
            return "ERROR", f"Failed to load CrossEncoder model {self.model_name}."
        if not self.model:
            return "SKIPPED", "NLI model not available (sentence-transformers missing or model failed to load)."

        # CrossEncoder predicts [contradiction, neutral, entailment]
        # For nli-deberta-v3-small, the scores are usually mapped to these 3 classes.
        # predict() returns a 2D array for the batch.
        prediction = self.model.predict([(source_text, claim)])
        scores = prediction[0]
        
        # Depending on the model, the order of labels might vary.
        # For deberta-v3-small NLI, labels are: 0: contradiction, 1: neutral, 2: entailment
        label_mapping = ["contradiction", "neutral", "entailment"]
        max_score_idx = scores.argmax()
        label = label_mapping[max_score_idx]
        score = scores[max_score_idx]

        if label == "entailment":
            return "PASS", f"Source text strictly entails the claim (score: {score:.4f})"
        elif label == "contradiction":
            return "FAIL", f"Source text contradicts the claim (score: {score:.4f})"
        else:
            return "FAIL", f"Source text is neutral/insufficient to support the claim (score: {score:.4f})"

# Singleton instance for the service
verifier = Verifier()

