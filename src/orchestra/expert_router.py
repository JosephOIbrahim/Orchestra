"""
Expert Router (Cognitive Safety MoE)
====================================

Routes incoming signals to intervention experts using FIXED priority,
first-match-wins semantics.

Expert Priority (from CLAUDE.md):
1. Validator   - frustrated, RED, caps, negative → empathy first
2. Scaffolder  - overwhelmed, stuck, too_many → break down, reduce scope
3. Restorer    - depleted, ORANGE, post-crash → easy wins, rest is OK
4. Refocuser   - distracted, tangent_over → gentle redirect
5. Celebrator  - task_complete, milestone → acknowledge win
6. Socratic    - exploring, high_energy, what if → guide discovery
7. Direct      - focused, hyperfocused, flow → stay out of way

ThinkingMachines [He2025] Compliance:
- FIXED expert priority (never reorder)
- First-match-wins (no backtracking)
- Deterministic routing (same signals → same expert)

Constitutional Principles:
- Safety first: Emotional safety before productivity
- User knows best: Their signal trumps our guess
"""

from dataclasses import dataclass, field
from typing import Optional, Dict, Any, Tuple, TYPE_CHECKING
from enum import Enum
import logging

from .prism_detector import SignalVector
from .cognitive_state import BurnoutLevel, EnergyLevel, MomentumPhase

if TYPE_CHECKING:
    from .bcm_trail import OrchestraTrail

logger = logging.getLogger(__name__)


# =============================================================================
# Expert Definitions - FIXED Priority Order
# =============================================================================

class Expert(Enum):
    """Intervention experts in FIXED priority order."""
    # ADHD_MoE Experts (1-7)
    VALIDATOR = "validator"      # 1 - Safety/emotional
    SCAFFOLDER = "scaffolder"    # 2 - Reducing overwhelm
    RESTORER = "restorer"        # 3 - Recovery
    REFOCUSER = "refocuser"      # 4 - Redirect
    CELEBRATOR = "celebrator"    # 5 - Win/dopamine
    SOCRATIC = "socratic"        # 6 - Exploration
    DIRECT = "direct"            # 7 - Minimal friction

    # v6.0.0: GROUNDING_MoE Experts (G1-G4)
    ORACLE_RESOLVER = "oracle_resolver"    # G1 - Reconcile oracle conflicts
    EVIDENCE_BUILDER = "evidence_builder"  # G2 - Build evidence chains
    CONFIDENCE_ADJ = "confidence_adj"      # G3 - Adjust confidence on hallucination
    ACCESS_GATEKEEPER = "access_gatekeeper"  # G4 - Route to grounding layer


# Expert trigger conditions (evaluated in FIXED order)
EXPERT_TRIGGERS = {
    Expert.VALIDATOR: {
        "emotional": ["frustrated", "angry", "overwhelmed"],
        "burnout": [BurnoutLevel.RED],
        "caps_detected": True,
        "description": "Empathy first, normalize struggle"
    },
    Expert.SCAFFOLDER: {
        "emotional": ["overwhelmed", "stuck"],
        "signals": ["too_many", "can't handle", "where do I start"],
        "description": "Break down, reduce scope, provide structure"
    },
    Expert.RESTORER: {
        "energy": [EnergyLevel.DEPLETED, EnergyLevel.LOW],
        "burnout": [BurnoutLevel.ORANGE],
        "momentum": [MomentumPhase.CRASHED],
        "description": "Easy wins, rest is OK, recovery mode"
    },
    Expert.REFOCUSER: {
        "signals": ["tangent", "off-topic", "anyway", "but also"],
        "tangent_budget_depleted": True,
        "description": "Gentle redirect to goal"
    },
    Expert.CELEBRATOR: {
        "signals": ["done", "finished", "completed", "works", "fixed"],
        "task_completed": True,
        "description": "Acknowledge win, dopamine boost"
    },
    Expert.SOCRATIC: {
        "mode": ["exploring", "teaching"],
        "signals": ["what if", "could we", "I wonder", "explore", "brainstorm"],
        "energy": [EnergyLevel.HIGH],
        "description": "Guide discovery, follow threads"
    },
    Expert.DIRECT: {
        "mode": ["focused"],
        "momentum": [MomentumPhase.ROLLING, MomentumPhase.PEAK],
        "burnout": [BurnoutLevel.GREEN],
        "description": "Stay out of way, minimal friction"
    }
}

# FIXED priority order - NEVER change this
EXPERT_PRIORITY = [
    Expert.VALIDATOR,
    Expert.SCAFFOLDER,
    Expert.RESTORER,
    Expert.REFOCUSER,
    Expert.CELEBRATOR,
    Expert.SOCRATIC,
    Expert.DIRECT
]

# v6.0.0: GROUNDING_MoE priority order (evaluated separately from ADHD_MoE)
GROUNDING_EXPERT_PRIORITY = [
    Expert.ORACLE_RESOLVER,    # G1 - Highest grounding priority
    Expert.EVIDENCE_BUILDER,   # G2
    Expert.CONFIDENCE_ADJ,     # G3
    Expert.ACCESS_GATEKEEPER,  # G4
]

# v6.0.0: GROUNDING_MoE trigger conditions
GROUNDING_EXPERT_TRIGGERS = {
    Expert.ORACLE_RESOLVER: {
        "signals": ["oracle_conflict", "mismatch", "inconsistent", "disagree"],
        "grounding_types": ["physics", "simulate"],
        "description": "Reconcile conflicting oracle sources"
    },
    Expert.EVIDENCE_BUILDER: {
        "signals": ["cite_needed", "source_request", "prove", "evidence", "justify"],
        "description": "Build evidence chain from claims to sources"
    },
    Expert.CONFIDENCE_ADJ: {
        "signals": ["hallucination_detected", "speculation", "uncertain", "might be wrong"],
        "hallucination_score_threshold": 0.5,
        "description": "Adjust confidence and add caveats"
    },
    Expert.ACCESS_GATEKEEPER: {
        "signals": ["oracle_required", "need ground truth", "verify", "check simulation"],
        "grounding_types": ["physics", "simulate", "oracle_needed"],
        "description": "Route query to grounding layer for oracle access"
    }
}


# =============================================================================
# Routing Result
# =============================================================================

@dataclass
class RoutingResult:
    """
    Result of expert routing.

    Contains the selected expert, trigger reason, and gate status.
    v6.0.0: Added grounding expert routing.
    v7.0.0: Added BCM trail confidence metadata.
    """
    expert: Expert
    trigger: str
    constitutional_pass: bool = True
    safety_gate_pass: bool = True
    safety_redirect: Optional[str] = None
    priority_index: int = 7  # 1-7, lower = higher priority

    # v6.0.0: Grounding expert (can be active alongside ADHD_MoE expert)
    grounding_expert: Optional[Expert] = None
    grounding_trigger: Optional[str] = None
    requires_grounding: bool = False

    # v7.0.0: BCM Trail confidence metadata
    # Note: These are METADATA ONLY - they do NOT affect expert selection order
    bcm_confidence: float = 1.0  # Trail-based confidence for selected expert [0.0-1.0]
    bcm_expert_confidences: Dict[str, float] = field(default_factory=dict)  # All expert confidences
    bcm_trail_version: str = ""  # Trail version for reproducibility
    bcm_enhanced: bool = False  # Whether BCM data was available

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dict for WebSocket."""
        return {
            "expert": self.expert.value,
            "trigger": self.trigger,
            "constitutional_pass": self.constitutional_pass,
            "safety_gate_pass": self.safety_gate_pass,
            "safety_redirect": self.safety_redirect,
            "priority_index": self.priority_index,
            # v6.0.0: Grounding fields
            "grounding_expert": self.grounding_expert.value if self.grounding_expert else None,
            "grounding_trigger": self.grounding_trigger,
            "requires_grounding": self.requires_grounding,
            # v7.0.0: BCM fields
            "bcm_confidence": self.bcm_confidence,
            "bcm_expert_confidences": self.bcm_expert_confidences,
            "bcm_trail_version": self.bcm_trail_version,
            "bcm_enhanced": self.bcm_enhanced
        }


# =============================================================================
# Expert Router
# =============================================================================

class ExpertRouter:
    """
    Routes signals to intervention experts.

    Implements Cognitive Safety MoE from CLAUDE.md with:
    - FIXED priority order (1-7)
    - First-match-wins semantics
    - Safety gates for constitutional compliance
    - Deterministic routing (same inputs → same output)

    v6.0.0: Added GROUNDING_MoE expert routing for oracle queries.
    """

    def __init__(self):
        """Initialize router."""
        self._last_routing: Optional[RoutingResult] = None
        self._last_grounding_routing: Optional[Tuple[Expert, str]] = None

    def route(
        self,
        signals: SignalVector,
        burnout: BurnoutLevel,
        energy: EnergyLevel,
        momentum: MomentumPhase,
        mode: str = "focused",
        tangent_budget: int = 5,
        task_completed: bool = False,
        caps_detected: bool = False,
        hallucination_score: float = 0.0,  # v6.0.0
        trail: Optional['OrchestraTrail'] = None  # v7.0.0: BCM trail for confidence metadata
    ) -> RoutingResult:
        """
        Route to expert based on signals and state.

        ThinkingMachines [He2025]: Fixed evaluation order, first-match-wins.
        v6.0.0: Added GROUNDING_MoE expert routing.
        v7.0.0: Added BCM trail confidence metadata (does NOT affect routing order).

        Args:
            signals: PRISM signal vector
            burnout: Current burnout level
            energy: Current energy level
            momentum: Current momentum phase
            mode: Current cognitive mode
            tangent_budget: Remaining tangent budget
            task_completed: Whether a task was just completed
            caps_detected: Whether ALL CAPS was detected
            hallucination_score: v6.0.0 - Hallucination detection score
            trail: v7.0.0 - BCM trail for confidence metadata (optional)

        Returns:
            RoutingResult with selected expert and reasoning
        """
        # =================================================================
        # GATE 1: Constitutional Check
        # =================================================================
        # Constitutional principles are NEVER violated
        constitutional_pass = self._check_constitutional(burnout, energy)

        # =================================================================
        # GATE 2: Safety Gate
        # =================================================================
        # Safety states force specific experts
        safety_result = self._check_safety_gate(burnout, energy, signals, caps_detected)

        if safety_result is not None:
            # v7.0.0: Add BCM confidence metadata to safety result
            self._apply_bcm_metadata(safety_result, trail)
            self._last_routing = safety_result
            logger.info(f"Safety gate → {safety_result.expert.value}: {safety_result.trigger}")
            return safety_result

        # =================================================================
        # GATE 3: Cognitive Safety MoE Routing (FIXED priority, first-match-wins)
        # =================================================================
        context = {
            "signals": signals,
            "burnout": burnout,
            "energy": energy,
            "momentum": momentum,
            "mode": mode,
            "tangent_budget": tangent_budget,
            "task_completed": task_completed,
            "caps_detected": caps_detected
        }

        # Evaluate in FIXED priority order
        for priority_idx, expert in enumerate(EXPERT_PRIORITY, start=1):
            trigger = self._check_expert_triggers(expert, context)
            if trigger:
                result = RoutingResult(
                    expert=expert,
                    trigger=trigger,
                    constitutional_pass=constitutional_pass,
                    safety_gate_pass=True,
                    priority_index=priority_idx
                )

                # v6.0.0: Check for GROUNDING_MoE expert (runs in parallel)
                grounding_result = self._route_grounding(signals, hallucination_score)
                if grounding_result:
                    result.grounding_expert, result.grounding_trigger = grounding_result
                    result.requires_grounding = True

                # v7.0.0: Add BCM confidence metadata
                self._apply_bcm_metadata(result, trail)

                self._last_routing = result
                logger.info(f"CognitiveSafetyMoE → {expert.value} (priority {priority_idx}): {trigger}")
                return result

        # Default to Direct (should always match, but safety fallback)
        result = RoutingResult(
            expert=Expert.DIRECT,
            trigger="default_fallback",
            constitutional_pass=constitutional_pass,
            priority_index=7
        )

        # v6.0.0: Check for GROUNDING_MoE expert (runs in parallel)
        grounding_result = self._route_grounding(signals, hallucination_score)
        if grounding_result:
            result.grounding_expert, result.grounding_trigger = grounding_result
            result.requires_grounding = True

        # v7.0.0: Add BCM confidence metadata
        self._apply_bcm_metadata(result, trail)

        self._last_routing = result
        return result

    def _check_constitutional(self, burnout: BurnoutLevel, energy: EnergyLevel) -> bool:
        """
        Check constitutional principles (safety floors).

        Constitutional principles from CLAUDE.md:
        1. Safety first: Emotional safety before productivity
        2. User knows best: Their signal trumps our guess
        3. Rest is productive: Recovery without guilt

        Returns:
            True if constitutional (always True - we enforce, not fail)
        """
        # We don't fail constitutional checks - we ENFORCE them via safety gate
        # This check is for logging/tracking
        return True

    def _check_safety_gate(
        self,
        burnout: BurnoutLevel,
        energy: EnergyLevel,
        signals: SignalVector,
        caps_detected: bool
    ) -> Optional[RoutingResult]:
        """
        Safety gate: Force specific experts for critical states.

        Per CLAUDE.md:
        - frustrated|RED|caps → Validator (empathy first, full stop)
        - overwhelmed|stuck → Scaffolder (break down, reduce scope)
        - depleted|ORANGE → Restorer (easy wins, rest is OK)

        Returns:
            RoutingResult if safety redirect needed, None otherwise
        """
        # RED burnout → Validator (full stop, empathy)
        if burnout == BurnoutLevel.RED:
            return RoutingResult(
                expert=Expert.VALIDATOR,
                trigger="RED_burnout",
                constitutional_pass=True,
                safety_gate_pass=False,
                safety_redirect="validator",
                priority_index=1
            )

        # ALL CAPS detected → Validator
        if caps_detected:
            return RoutingResult(
                expert=Expert.VALIDATOR,
                trigger="caps_detected",
                constitutional_pass=True,
                safety_gate_pass=False,
                safety_redirect="validator",
                priority_index=1
            )

        # High emotional score → Validator
        if signals.requires_intervention():
            return RoutingResult(
                expert=Expert.VALIDATOR,
                trigger=f"emotional_score_{signals.emotional_score:.2f}",
                constitutional_pass=True,
                safety_gate_pass=False,
                safety_redirect="validator",
                priority_index=1
            )

        # ORANGE burnout + low energy → Restorer
        if burnout == BurnoutLevel.ORANGE and energy in (EnergyLevel.LOW, EnergyLevel.DEPLETED):
            return RoutingResult(
                expert=Expert.RESTORER,
                trigger="ORANGE_burnout_low_energy",
                constitutional_pass=True,
                safety_gate_pass=False,
                safety_redirect="restorer",
                priority_index=3
            )

        # Depleted energy → Restorer
        if energy == EnergyLevel.DEPLETED:
            return RoutingResult(
                expert=Expert.RESTORER,
                trigger="energy_depleted",
                constitutional_pass=True,
                safety_gate_pass=False,
                safety_redirect="restorer",
                priority_index=3
            )

        return None

    def _check_expert_triggers(self, expert: Expert, context: Dict[str, Any]) -> Optional[str]:
        """
        Check if an expert's triggers match the current context.

        Returns:
            Trigger reason if matched, None otherwise
        """
        triggers = EXPERT_TRIGGERS.get(expert, {})
        signals = context["signals"]
        burnout = context["burnout"]
        energy = context["energy"]
        momentum = context["momentum"]
        mode = context["mode"]

        # Check emotional signals
        if "emotional" in triggers:
            for emotion in triggers["emotional"]:
                if signals.emotional.get(emotion, 0) > 0:
                    return f"emotional_{emotion}"

        # Check burnout levels
        if "burnout" in triggers:
            if burnout in triggers["burnout"]:
                return f"burnout_{burnout.value}"

        # Check energy levels
        if "energy" in triggers:
            if energy in triggers["energy"]:
                return f"energy_{energy.value}"

        # Check momentum phases
        if "momentum" in triggers:
            if momentum in triggers["momentum"]:
                return f"momentum_{momentum.value}"

        # Check mode
        if "mode" in triggers:
            if mode in triggers["mode"]:
                return f"mode_{mode}"

        # Check text signals (from SignalVector)
        if "signals" in triggers:
            # Check mode signals
            for sig in triggers["signals"]:
                if signals.mode.get(sig, 0) > 0:
                    return f"signal_{sig}"
                if signals.task.get(sig, 0) > 0:
                    return f"signal_{sig}"

        # Check caps
        if triggers.get("caps_detected") and context.get("caps_detected"):
            return "caps_detected"

        # Check tangent budget
        if triggers.get("tangent_budget_depleted") and context.get("tangent_budget", 5) <= 0:
            return "tangent_budget_depleted"

        # Check task completion
        if triggers.get("task_completed") and context.get("task_completed"):
            return "task_completed"

        return None

    def _apply_bcm_metadata(
        self,
        result: RoutingResult,
        trail: Optional['OrchestraTrail']
    ) -> None:
        """
        v7.0.0: Apply BCM trail confidence metadata to routing result.

        IMPORTANT: This method adds METADATA ONLY. It does NOT affect
        expert selection, which is determined by FIXED priority order.

        ThinkingMachines [He2025] Compliance:
        - BCM data is informational/observational
        - Same routing order regardless of trail state
        - Confidence values are for downstream use (UI, logging, learning)

        Args:
            result: RoutingResult to enhance with BCM metadata
            trail: Optional BCM trail (if None, defaults are used)
        """
        if trail is None:
            # No trail available - use defaults
            result.bcm_confidence = 1.0
            result.bcm_expert_confidences = {}
            result.bcm_trail_version = ""
            result.bcm_enhanced = False
            return

        # Get confidence for selected expert
        result.bcm_confidence = trail.get_expert_confidence(result.expert.value)

        # Get all expert confidences for downstream use
        result.bcm_expert_confidences = {
            expert.value: trail.get_expert_confidence(expert.value)
            for expert in EXPERT_PRIORITY
        }

        # Track trail version for reproducibility
        result.bcm_trail_version = trail.version
        result.bcm_enhanced = True

        logger.debug(
            f"BCM metadata: expert={result.expert.value}, "
            f"confidence={result.bcm_confidence:.2f}, "
            f"trail_version={result.bcm_trail_version}"
        )

    def _route_grounding(
        self,
        signals: SignalVector,
        hallucination_score: float = 0.0
    ) -> Optional[Tuple[Expert, str]]:
        """
        v6.0.0: Route to GROUNDING_MoE expert if needed.

        Evaluates grounding signals to determine if oracle access is required.
        Runs in parallel with ADHD_MoE routing.

        Args:
            signals: PRISM signal vector with grounding signals
            hallucination_score: Detected hallucination score

        Returns:
            Tuple of (Expert, trigger) or None if no grounding needed
        """
        # Check if grounding signals present
        if not hasattr(signals, 'grounding') or not signals.grounding:
            # Check for hallucination-triggered confidence adjustment
            if hallucination_score >= 0.5:
                return (Expert.CONFIDENCE_ADJ, f"hallucination_score_{hallucination_score:.2f}")
            return None

        grounding_type = getattr(signals, 'grounding_type', None)
        grounding_score = getattr(signals, 'grounding_score', 0.0)

        # Evaluate GROUNDING_MoE experts in FIXED priority order
        for expert in GROUNDING_EXPERT_PRIORITY:
            triggers = GROUNDING_EXPERT_TRIGGERS.get(expert, {})

            # Check grounding types
            if "grounding_types" in triggers:
                if grounding_type in triggers["grounding_types"]:
                    return (expert, f"grounding_type_{grounding_type}")

            # Check hallucination threshold
            if "hallucination_score_threshold" in triggers:
                threshold = triggers["hallucination_score_threshold"]
                if hallucination_score >= threshold:
                    return (expert, f"hallucination_score_{hallucination_score:.2f}")

            # Check text signals
            if "signals" in triggers:
                for sig in triggers["signals"]:
                    if signals.grounding.get(sig, 0) > 0:
                        return (expert, f"grounding_signal_{sig}")

        # High grounding score → route to ACCESS_GATEKEEPER
        if grounding_score >= 0.5:
            return (Expert.ACCESS_GATEKEEPER, f"grounding_score_{grounding_score:.2f}")

        return None

    def get_last_routing(self) -> Optional[RoutingResult]:
        """Get the last routing result."""
        return self._last_routing

    def get_expert_info(self, expert: Expert) -> Dict[str, Any]:
        """Get information about an expert (ADHD_MoE or GROUNDING_MoE)."""
        # Check ADHD_MoE first
        if expert in EXPERT_PRIORITY:
            triggers = EXPERT_TRIGGERS.get(expert, {})
            return {
                "name": expert.value,
                "priority": EXPERT_PRIORITY.index(expert) + 1,
                "type": "adhd_moe",
                "description": triggers.get("description", ""),
                "triggers": {k: v for k, v in triggers.items() if k != "description"}
            }

        # v6.0.0: Check GROUNDING_MoE
        if expert in GROUNDING_EXPERT_PRIORITY:
            triggers = GROUNDING_EXPERT_TRIGGERS.get(expert, {})
            return {
                "name": expert.value,
                "priority": GROUNDING_EXPERT_PRIORITY.index(expert) + 1,
                "type": "grounding_moe",
                "description": triggers.get("description", ""),
                "triggers": {k: v for k, v in triggers.items() if k != "description"}
            }

        return {"name": expert.value, "type": "unknown"}


# =============================================================================
# Factory Function
# =============================================================================

def create_router() -> ExpertRouter:
    """Create an ExpertRouter instance."""
    return ExpertRouter()


__all__ = [
    'Expert', 'RoutingResult', 'ExpertRouter',
    'EXPERT_TRIGGERS', 'EXPERT_PRIORITY',
    # v6.0.0: GROUNDING_MoE exports
    'GROUNDING_EXPERT_TRIGGERS', 'GROUNDING_EXPERT_PRIORITY',
    'create_router'
]
