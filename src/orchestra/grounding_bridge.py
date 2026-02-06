"""
Grounding Bridge
================

Adapter between Orchestra core and the Grounding Layer (L7.5) subsystem.

This bridge connects the NEXUS Pipeline to the grounding modules:
- OracleRegistry: Oracle registration and lookup
- EvidenceWarehouse: Provenance tracking and caching
- SourceRouter: LEARN|ACCESS|HYBRID mode routing
- HallucinationDetector: Speculation and claim detection

v6.0.0 Extension: Phases 0b (CLASSIFY) and 0c (GROUND)

ThinkingMachines [He2025] Compliance:
- FIXED evaluation order for grounding classification
- Deterministic source mode routing
- Batch-invariant oracle queries (time-windowed)

Reference: [GWM2026] "Grounded World Models: Deterministic Physics Reasoning"
Core Thesis: "LLMs don't need to LEARN physics—they need ACCESS to physics"
"""

import sys
import time
import logging
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple

logger = logging.getLogger(__name__)

# =============================================================================
# Import Grounding Subsystem
# =============================================================================

# Path to grounding subsystem
GROUNDING_PATH = Path.home() / ".claude" / "substrate" / "grounding"

# Lazy import grounding modules (may not be available in all deployments)
_grounding_available = False
_oracle_registry = None
_evidence_warehouse = None
_source_router = None
_hallucination_detector = None


def _ensure_grounding_imports():
    """
    Lazy import of grounding subsystem modules.

    Graceful degradation: If grounding modules unavailable,
    bridge operates in LEARN-only mode.
    """
    global _grounding_available
    global _oracle_registry, _evidence_warehouse, _source_router, _hallucination_detector

    if _grounding_available:
        return True

    if not GROUNDING_PATH.exists():
        logger.warning(f"Grounding subsystem not found at {GROUNDING_PATH}")
        return False

    try:
        # Add grounding path to sys.path
        grounding_str = str(GROUNDING_PATH)
        if grounding_str not in sys.path:
            sys.path.insert(0, grounding_str)

        # Import modules
        import oracle_registry as _oracle_registry
        import evidence_warehouse as _evidence_warehouse
        import source_router as _source_router
        import hallucination_detector as _hallucination_detector

        _grounding_available = True
        logger.info("Grounding subsystem loaded successfully")
        return True

    except ImportError as e:
        logger.warning(f"Failed to import grounding subsystem: {e}")
        return False


# =============================================================================
# Source Mode (v6.0.0)
# =============================================================================

class SourceMode(Enum):
    """
    Source mode for grounding decisions.

    From [GWM2026]:
    - LEARN: No oracle available, use LLM inference (default)
    - ACCESS: Oracle exists, query for ground truth
    - HYBRID: Oracle result + LLM interpretation
    """
    LEARN = "learn"
    ACCESS = "access"
    HYBRID = "hybrid"


# =============================================================================
# Grounding Result
# =============================================================================

@dataclass
class GroundingResult:
    """
    Result from grounding phase (0b + 0c).

    Contains source mode classification and any oracle/evidence data.
    """
    # Phase 0b: CLASSIFY
    source_mode: SourceMode = SourceMode.LEARN
    classification_reason: str = "default"
    grounding_signals: List[str] = field(default_factory=list)

    # Phase 0c: GROUND (if ACCESS or HYBRID)
    oracle_id: Optional[str] = None
    oracle_result: Optional[Dict[str, Any]] = None
    oracle_latency_ms: float = 0.0

    # Evidence tracking
    evidence_chain_id: Optional[str] = None
    evidence_count: int = 0
    confidence: float = 0.0

    # Hallucination detection
    hallucination_score: float = 0.0
    speculation_detected: bool = False
    caveats_needed: List[str] = field(default_factory=list)

    # Metadata
    timestamp: float = field(default_factory=time.time)
    grounding_budget_remaining: int = 5

    def is_grounded(self) -> bool:
        """Check if response is grounded in oracle/evidence."""
        return self.source_mode in (SourceMode.ACCESS, SourceMode.HYBRID)

    def to_anchor_component(self) -> str:
        """
        Generate anchor component for EXEC anchor.

        v6.0.0 extended format:
        [EXEC:...|grounding:{mode}:{confidence}]
        """
        conf_str = f"{self.confidence:.2f}" if self.confidence > 0 else "na"
        return f"{self.source_mode.value}:{conf_str}"

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dict for dashboard/WebSocket."""
        return {
            "source_mode": self.source_mode.value,
            "classification_reason": self.classification_reason,
            "grounding_signals": self.grounding_signals,
            "oracle_id": self.oracle_id,
            "oracle_result": self.oracle_result,
            "oracle_latency_ms": self.oracle_latency_ms,
            "evidence_chain_id": self.evidence_chain_id,
            "evidence_count": self.evidence_count,
            "confidence": self.confidence,
            "hallucination_score": self.hallucination_score,
            "speculation_detected": self.speculation_detected,
            "caveats_needed": self.caveats_needed,
            "timestamp": self.timestamp,
            "grounding_budget_remaining": self.grounding_budget_remaining,
            "is_grounded": self.is_grounded()
        }


# =============================================================================
# Grounding Signal Patterns (v6.0.0)
# =============================================================================

# FIXED signal patterns for grounding classification
# Evaluated in order: physics > factual > calculate > simulate
GROUNDING_SIGNALS = {
    "physics": [
        "position", "velocity", "acceleration", "force", "collision",
        "bounce", "fall", "gravity", "trajectory", "momentum", "mass",
        "friction", "rigid body", "rbd", "physics", "simulation"
    ],
    "factual": [
        "what is", "define", "explain", "who is", "when did", "where is",
        "how many", "how much", "fact", "true", "false", "verify"
    ],
    "calculate": [
        "calculate", "compute", "solve", "equation", "formula", "math",
        "number", "result", "answer", "value", "distance", "time"
    ],
    "simulate": [
        "simulate", "predict", "forecast", "model", "step", "frame",
        "render", "bake", "cache", "houdini", "bullet"
    ]
}

# Signals that force HYBRID mode (need LLM interpretation)
HYBRID_SIGNALS = [
    "why", "explain why", "how come", "reason", "cause", "because"
]


# =============================================================================
# Grounding Bridge
# =============================================================================

class GroundingBridge:
    """
    Adapter between Orchestra NEXUS Pipeline and Grounding Layer (L7.5).

    Provides:
    - Phase 0b: CLASSIFY - Determine source mode (LEARN|ACCESS|HYBRID)
    - Phase 0c: GROUND - Query oracle if needed
    - Hallucination detection for LLM outputs
    - Evidence chain management

    ThinkingMachines [He2025] Compliance:
    - FIXED signal evaluation order
    - Deterministic mode classification
    - Time-windowed oracle determinism
    """

    def __init__(self, grounding_budget: int = 5):
        """
        Initialize grounding bridge.

        Args:
            grounding_budget: Max oracle queries per session (depletes like tangent_budget)
        """
        self.grounding_budget = grounding_budget
        self._available = _ensure_grounding_imports()

        # Initialize subsystem components if available
        self._registry = None
        self._warehouse = None
        self._router = None
        self._detector = None

        if self._available:
            try:
                self._registry = _oracle_registry.OracleRegistry()  # type: ignore[union-attr]
                self._warehouse = _evidence_warehouse.EvidenceWarehouse()  # type: ignore[union-attr]
                self._router = _source_router.SourceRouter()  # type: ignore[union-attr]
                self._detector = _hallucination_detector.HallucinationDetector()  # type: ignore[union-attr]
                logger.info("Grounding bridge initialized with full subsystem")
            except Exception as e:
                logger.warning(f"Grounding subsystem init failed: {e}")
                self._available = False

    def is_available(self) -> bool:
        """Check if grounding subsystem is available."""
        return self._available

    # =========================================================================
    # Phase 0b: CLASSIFY
    # =========================================================================

    def classify_query(
        self,
        message: str,
        context: Optional[Dict[str, Any]] = None
    ) -> Tuple[SourceMode, str, List[str]]:
        """
        Phase 0b: Classify query to determine source mode.

        ThinkingMachines [He2025]: FIXED evaluation order for signals.

        Args:
            message: User message to classify
            context: Optional context (active domain, etc.)

        Returns:
            Tuple of (SourceMode, reason, detected_signals)
        """
        context = context or {}
        message_lower = message.lower()
        detected_signals = []

        # Check for explicit mode override in context
        if context.get("force_source_mode"):
            mode = SourceMode(context["force_source_mode"])
            return (mode, "context_override", [])

        # FIXED evaluation order: physics > factual > calculate > simulate
        signal_order = ["physics", "factual", "calculate", "simulate"]
        matched_category = None

        for category in signal_order:
            keywords = GROUNDING_SIGNALS[category]
            for keyword in keywords:
                if keyword in message_lower:
                    detected_signals.append(f"{category}:{keyword}")
                    if matched_category is None:
                        matched_category = category

        # No grounding signals → LEARN mode
        if not detected_signals:
            return (SourceMode.LEARN, "no_grounding_signals", [])

        # Check for HYBRID signals (why/explain)
        for signal in HYBRID_SIGNALS:
            if signal in message_lower:
                detected_signals.append(f"hybrid:{signal}")
                return (SourceMode.HYBRID, f"hybrid_signal_{signal}", detected_signals)

        # Check if we have an oracle for this category
        if self._available and self._registry:
            try:
                # Use router for more sophisticated classification
                routing_decision = self._router.classify(message)  # type: ignore[union-attr]
                mode = SourceMode(routing_decision.mode.value)
                return (mode, f"router_{routing_decision.reason}", detected_signals)
            except Exception as e:
                logger.warning(f"Router classification failed: {e}")

        # Default: If physics/simulate signals, suggest ACCESS
        if matched_category in ("physics", "simulate"):
            return (SourceMode.ACCESS, f"oracle_signal_{matched_category}", detected_signals)

        # Factual/calculate → HYBRID (need LLM to format answer)
        if matched_category in ("factual", "calculate"):
            return (SourceMode.HYBRID, f"hybrid_signal_{matched_category}", detected_signals)

        return (SourceMode.LEARN, "default", detected_signals)

    # =========================================================================
    # Phase 0c: GROUND
    # =========================================================================

    def query_oracle(
        self,
        query_type: str,
        params: Dict[str, Any],
        source_mode: SourceMode
    ) -> GroundingResult:
        """
        Phase 0c: Query oracle for ground truth if ACCESS/HYBRID mode.

        Args:
            query_type: Type of query (e.g., "get_position", "collision_check")
            params: Query parameters
            source_mode: Determined source mode from classify_query

        Returns:
            GroundingResult with oracle data (or empty if LEARN mode)
        """
        result = GroundingResult(
            source_mode=source_mode,
            grounding_budget_remaining=self.grounding_budget
        )

        # LEARN mode: No oracle query
        if source_mode == SourceMode.LEARN:
            result.classification_reason = "learn_mode_no_oracle"
            return result

        # Check grounding budget
        if self.grounding_budget <= 0:
            result.source_mode = SourceMode.LEARN
            result.classification_reason = "grounding_budget_depleted"
            return result

        # Subsystem not available: Fall back to LEARN
        if not self._available or not self._registry:
            result.source_mode = SourceMode.LEARN
            result.classification_reason = "subsystem_unavailable"
            return result

        # Find oracle for query type
        try:
            oracle = self._registry.find_oracle_for_query(query_type)

            if oracle is None:
                result.source_mode = SourceMode.LEARN
                result.classification_reason = "no_oracle_for_query"
                return result

            # Query oracle
            start_time = time.time()
            oracle_result = oracle.query(query_type, params)
            latency = (time.time() - start_time) * 1000

            # Consume budget
            self.grounding_budget -= 1

            # Build result
            result.oracle_id = oracle.oracle_id
            result.oracle_result = oracle_result
            result.oracle_latency_ms = latency
            result.confidence = 1.0  # Oracle results have 100% confidence
            result.grounding_budget_remaining = self.grounding_budget
            result.classification_reason = f"oracle_{oracle.oracle_id}"

            # Record evidence
            if self._warehouse:
                evidence = self._warehouse.record_evidence(
                    query_type=query_type,
                    params=params,
                    result=oracle_result,
                    source=f"oracle:{oracle.oracle_id}"
                )
                result.evidence_chain_id = evidence.chain_id
                result.evidence_count = 1

            logger.info(f"Oracle query: {oracle.oracle_id} ({latency:.1f}ms)")
            return result

        except Exception as e:
            logger.error(f"Oracle query failed: {e}")
            result.source_mode = SourceMode.LEARN
            result.classification_reason = f"oracle_error_{str(e)[:50]}"
            return result

    # =========================================================================
    # Hallucination Detection
    # =========================================================================

    def detect_hallucination(
        self,
        claim: str,
        source_mode: SourceMode,
        oracle_result: Optional[Dict[str, Any]] = None
    ) -> Tuple[float, bool, List[str]]:
        """
        Detect potential hallucination in LLM output.

        Args:
            claim: The LLM-generated claim to check
            source_mode: Current source mode
            oracle_result: Oracle result to compare against (if available)

        Returns:
            Tuple of (hallucination_score, speculation_detected, caveats_needed)
        """
        # Without detector, use heuristic analysis
        if not self._available or not self._detector:
            return self._heuristic_hallucination_check(claim, source_mode)

        try:
            score = self._detector.detect(claim, oracle_result)
            speculation = self._detector.detect_speculation(claim)
            caveats = self._detector.suggest_caveats(claim, source_mode.value)

            return (score.score, speculation, caveats)

        except Exception as e:
            logger.warning(f"Hallucination detection failed: {e}")
            return self._heuristic_hallucination_check(claim, source_mode)

    def _heuristic_hallucination_check(
        self,
        claim: str,
        source_mode: SourceMode
    ) -> Tuple[float, bool, List[str]]:
        """
        Heuristic hallucination detection when subsystem unavailable.

        Based on [GWM2026] speculation patterns.
        """
        claim_lower = claim.lower()
        score = 0.0
        speculation = False
        caveats = []

        # Speculation indicators
        speculation_words = [
            "probably", "likely", "might", "could be", "possibly",
            "i think", "i believe", "seems like", "appears to"
        ]

        for word in speculation_words:
            if word in claim_lower:
                speculation = True
                score += 0.2
                break

        # Physics claims in LEARN mode are risky
        physics_claims = [
            "will hit", "will land", "position is", "velocity is",
            "will collide", "will bounce", "will fall"
        ]

        for pattern in physics_claims:
            if pattern in claim_lower and source_mode == SourceMode.LEARN:
                score += 0.3
                caveats.append("Physics claim made without oracle verification")
                break

        # Absolute certainty in LEARN mode
        certainty_words = ["definitely", "certainly", "always", "never", "exactly"]
        for word in certainty_words:
            if word in claim_lower and source_mode == SourceMode.LEARN:
                score += 0.1
                caveats.append("High certainty language without ground truth")
                break

        score = min(score, 1.0)
        return (score, speculation, caveats)

    # =========================================================================
    # Evidence Chain
    # =========================================================================

    def build_evidence_chain(
        self,
        claims: List[str],
        sources: List[str]
    ) -> Optional[str]:
        """
        Build evidence chain linking claims to sources.

        Args:
            claims: List of claims made
            sources: List of sources (oracle IDs, evidence IDs)

        Returns:
            Evidence chain ID or None if warehouse unavailable
        """
        if not self._available or not self._warehouse:
            return None

        try:
            chain = self._warehouse.create_chain(claims, sources)
            return chain.chain_id
        except Exception as e:
            logger.warning(f"Evidence chain creation failed: {e}")
            return None

    # =========================================================================
    # Combined Grounding Flow
    # =========================================================================

    def process_grounding(
        self,
        message: str,
        context: Optional[Dict[str, Any]] = None
    ) -> GroundingResult:
        """
        Combined Phase 0b + 0c grounding flow.

        This is the main entry point for grounding in the NEXUS pipeline.

        Args:
            message: User message
            context: Optional context

        Returns:
            Complete GroundingResult
        """
        context = context or {}

        # Phase 0b: CLASSIFY
        source_mode, reason, signals = self.classify_query(message, context)

        result = GroundingResult(
            source_mode=source_mode,
            classification_reason=reason,
            grounding_signals=signals,
            grounding_budget_remaining=self.grounding_budget
        )

        # Phase 0c: GROUND (if ACCESS or HYBRID)
        if source_mode != SourceMode.LEARN and context.get("query_type"):
            grounding = self.query_oracle(
                query_type=context["query_type"],
                params=context.get("query_params", {}),
                source_mode=source_mode
            )

            # Merge oracle results into result
            result.oracle_id = grounding.oracle_id
            result.oracle_result = grounding.oracle_result
            result.oracle_latency_ms = grounding.oracle_latency_ms
            result.evidence_chain_id = grounding.evidence_chain_id
            result.evidence_count = grounding.evidence_count
            result.confidence = grounding.confidence
            result.grounding_budget_remaining = grounding.grounding_budget_remaining

        logger.debug(f"Grounding: {source_mode.value} ({reason}) - {len(signals)} signals")
        return result

    # =========================================================================
    # Budget Management
    # =========================================================================

    def reset_budget(self, budget: int = 5) -> None:
        """Reset grounding budget (e.g., on session reset)."""
        self.grounding_budget = budget

    def get_budget(self) -> int:
        """Get remaining grounding budget."""
        return self.grounding_budget


# =============================================================================
# Factory Function
# =============================================================================

def create_grounding_bridge(grounding_budget: int = 5) -> GroundingBridge:
    """
    Create a GroundingBridge instance.

    Args:
        grounding_budget: Max oracle queries per session

    Returns:
        Configured GroundingBridge
    """
    return GroundingBridge(grounding_budget=grounding_budget)


__all__ = [
    'SourceMode', 'GroundingResult', 'GroundingBridge',
    'GROUNDING_SIGNALS', 'create_grounding_bridge'
]
