"""
Cognitive Orchestrator
======================

Ties together all cognitive modules in the 8-Phase NEXUS Pipeline.

Pipeline (v6.0.0):
0.  RETRIEVE  - Knowledge check for factual queries (fast path)
0b. CLASSIFY  - Determine source mode (LEARN|ACCESS|HYBRID)
0c. GROUND    - Query oracle if ACCESS/HYBRID mode
1.  DETECT    - PRISM signal extraction (grounding-aware)
2.  CASCADE   - Constitutional/safety gates + Cognitive Safety MoE + GROUNDING_MoE
3.  LOCK      - Parameter locking with MAX3 bounds + source_mode
4.  EXECUTE   - Decision engine routing (work/delegate/protect)
5.  UPDATE    - RC^+xi convergence tracking + grounding metrics

ThinkingMachines [He2025] Compliance:
- State snapshot BEFORE processing (batch-invariance)
- FIXED evaluation order (8 phases, no reordering)
- FIXED signal priority (emotional > grounding > mode > domain > task)
- FIXED expert priority (Validator > ... > Direct, GROUNDING_MoE parallel)
- LOCKED parameters during generation
- Deterministic checksums
- Time-windowed oracle determinism

Reference: [GWM2026] "Grounded World Models: Deterministic Physics Reasoning"
Core Thesis: "LLMs don't need to LEARN physics—they need ACCESS to physics"

Usage:
    orchestrator = CognitiveOrchestrator()
    result = orchestrator.process_message("help me implement this feature")
    print(result.to_anchor())  # [EXEC:a3f2b8|direct|Cortex|30000ft|standard|learn:na]
"""

import time
from dataclasses import dataclass, field
from typing import Optional, Dict, Any
import logging

# Cognitive modules
from .prism_detector import PRISMDetector, SignalVector, create_detector
from .expert_router import ExpertRouter, Expert, RoutingResult, create_router
from .parameter_locker import (
    ParameterLocker, LockedParams, LockResult, ThinkDepth, Paradigm, create_locker
)
from .convergence_tracker import (
    ConvergenceTracker, ConvergenceResult, AttractorBasin, create_tracker
)
from .cognitive_state import (
    CognitiveState, CognitiveStateManager, BurnoutLevel, EnergyLevel,
    MomentumPhase, CognitiveMode, Altitude
)
# v6.0.0: Grounding Layer
from .grounding_bridge import (
    GroundingBridge, GroundingResult, SourceMode, create_grounding_bridge
)

logger = logging.getLogger(__name__)


# =============================================================================
# NEXUS Result
# =============================================================================

@dataclass
class NexusResult:
    """
    Complete result from the 8-Phase NEXUS Pipeline (v6.0.0).

    Contains all phase outputs for dashboard visualization and logging.
    """
    # Phase 0b/0c: GROUNDING (v6.0.0)
    grounding: Optional[GroundingResult] = None

    # Phase 1: DETECT
    signals: SignalVector = None

    # Phase 2: CASCADE
    routing: RoutingResult = None

    # Phase 3: LOCK
    lock: LockResult = None

    # Phase 5: UPDATE
    convergence: ConvergenceResult = None

    # Metadata
    timestamp: float = field(default_factory=time.time)
    processing_time_ms: float = 0.0
    state_checksum: str = ""

    def to_anchor(self) -> str:
        """
        Get anchor string for embedding in responses.

        v6.0.0 format: [EXEC:checksum|expert|paradigm|altitude|depth|grounding]
        """
        base_anchor = self.lock.params.to_anchor() if self.lock else "[EXEC:unknown]"

        # v6.0.0: Append grounding component
        if self.grounding:
            grounding_str = self.grounding.to_anchor_component()
            # Insert grounding into anchor format
            if base_anchor.endswith("]"):
                base_anchor = base_anchor[:-1] + f"|{grounding_str}]"

        return base_anchor

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dict for WebSocket/dashboard."""
        result = {
            # Phase 0b/0c: GROUNDING (v6.0.0)
            "source_mode": self.grounding.source_mode.value if self.grounding else "learn",
            "grounding_type": self.signals.grounding_type if self.signals else None,  # From PRISM signals
            "oracle_id": self.grounding.oracle_id if self.grounding else None,
            "oracle_latency_ms": self.grounding.oracle_latency_ms if self.grounding else 0.0,
            "grounding_confidence": self.grounding.confidence if self.grounding else 0.0,
            "hallucination_score": self.grounding.hallucination_score if self.grounding else 0.0,
            "grounding_budget_remaining": self.grounding.grounding_budget_remaining if self.grounding else 5,

            # Phase 1: DETECT - PRISM signals
            "signals_emotional": self._get_top_signal(self.signals.emotional) if self.signals else None,
            "signals_grounding": self.signals.grounding_type if self.signals else None,  # v6.0.0
            "signals_mode": self.signals.mode_detected if self.signals else None,
            "signals_domain": list(self.signals.domain.keys()) if self.signals and self.signals.domain else None,
            "signals_task": self.signals.primary_task if self.signals else None,
            "current_phase": "execute",  # After processing, we're at execute

            # Phase 2: CASCADE - Expert routing
            "constitutional_pass": self.routing.constitutional_pass if self.routing else True,
            "safety_gate_pass": self.routing.safety_gate_pass if self.routing else True,
            "safety_redirect": self.routing.safety_redirect if self.routing else None,
            "selected_expert": self.routing.expert.value if self.routing else "direct",
            "expert_trigger": self.routing.trigger if self.routing else "default",
            # v6.0.0: Grounding expert
            "grounding_expert": self.routing.grounding_expert.value if self.routing and self.routing.grounding_expert else None,
            "grounding_trigger": self.routing.grounding_trigger if self.routing else None,
            "requires_grounding": self.routing.requires_grounding if self.routing else False,

            # Phase 3: LOCK - Parameter locking
            "lock_status": self.lock.status.value if self.lock else "pending",
            "reflection_iteration": self.lock.params.reflection_iteration if self.lock else 0,
            "locked_expert": self.lock.params.expert if self.lock else "direct",
            "locked_paradigm": self.lock.params.paradigm if self.lock else "Cortex",
            "locked_altitude": self.lock.params.altitude if self.lock else "30000ft",
            "locked_think_depth": self.lock.params.think_depth if self.lock else "standard",
            "lock_checksum": self.lock.params.checksum if self.lock else "",

            # Phase 5: UPDATE - Convergence
            "epistemic_tension": self.convergence.epistemic_tension if self.convergence else 0.0,
            "epsilon": 0.1,
            "attractor_basin": self.convergence.attractor_basin.value if self.convergence else "focused",
            "stable_exchanges": self.convergence.stable_exchanges if self.convergence else 0,
            "converged": self.convergence.converged if self.convergence else False,
            "feedback_active": True,

            # Metadata
            "timestamp": self.timestamp,
            "processing_time_ms": self.processing_time_ms,
            "state_checksum": self.state_checksum
        }

        return result

    def _get_top_signal(self, signals: Dict[str, float]) -> Optional[str]:
        """Get top signal from dict."""
        if not signals:
            return None
        return max(signals.items(), key=lambda x: x[1])[0]


# =============================================================================
# Cognitive Orchestrator
# =============================================================================

class CognitiveOrchestrator:
    """
    Orchestrates the 5-Phase NEXUS Pipeline.

    This is the main entry point for cognitive processing. It:
    1. Takes a state snapshot (batch-invariance)
    2. Runs PRISM detection (DETECT)
    3. Routes to expert (CASCADE)
    4. Locks parameters (LOCK)
    5. Updates convergence (UPDATE)
    6. Commits state changes atomically
    """

    def __init__(
        self,
        state_manager: Optional[CognitiveStateManager] = None,
        detector: Optional[PRISMDetector] = None,
        router: Optional[ExpertRouter] = None,
        locker: Optional[ParameterLocker] = None,
        tracker: Optional[ConvergenceTracker] = None,
        grounding_bridge: Optional[GroundingBridge] = None  # v6.0.0
    ):
        """
        Initialize orchestrator with cognitive modules.

        Args:
            state_manager: State persistence manager (creates default if None)
            detector: PRISM signal detector (creates default if None)
            router: Expert router (creates default if None)
            locker: Parameter locker (creates default if None)
            tracker: Convergence tracker (creates default if None)
            grounding_bridge: v6.0.0 - Grounding layer bridge (creates default if None)
        """
        self.state_manager = state_manager or CognitiveStateManager()
        self.detector = detector or create_detector()
        self.router = router or create_router()
        self.locker = locker or create_locker()
        self.tracker = tracker or create_tracker()
        self.grounding = grounding_bridge or create_grounding_bridge()  # v6.0.0

        self._last_result: Optional[NexusResult] = None

    def process_message(
        self,
        message: str,
        context: Dict[str, Any] = None,
        requested_depth: ThinkDepth = ThinkDepth.STANDARD
    ) -> NexusResult:
        """
        Process a message through the 8-Phase NEXUS Pipeline (v6.0.0).

        ThinkingMachines [He2025]: Fixed evaluation order, deterministic routing.
        [GWM2026]: Grounding layer for ACCESS > LEARN paradigm.

        Pipeline: 0→0b→0c→1→2→3→4→5

        Args:
            message: The user message to process
            context: Optional context (active domain, query_type, query_params, etc.)
            requested_depth: User-requested thinking depth

        Returns:
            NexusResult with all phase outputs including grounding
        """
        start_time = time.time()
        context = context or {}

        # =================================================================
        # STEP 0: STATE SNAPSHOT (ThinkingMachines [He2025])
        # =================================================================
        state = self.state_manager.get_state()
        snapshot = state.snapshot()
        state_checksum = snapshot.checksum()

        logger.info(f"NEXUS Pipeline starting: state={state_checksum}")

        # =================================================================
        # PHASE 0b: CLASSIFY (v6.0.0 - Determine Source Mode)
        # =================================================================
        logger.debug("Phase 0b: CLASSIFY")

        grounding_result = self.grounding.process_grounding(message, context)

        logger.debug(f"  Source mode: {grounding_result.source_mode.value}, "
                     f"signals: {len(grounding_result.grounding_signals)}")

        # =================================================================
        # PHASE 0c: GROUND (v6.0.0 - Query Oracle if ACCESS/HYBRID)
        # =================================================================
        # Note: Grounding is already handled in process_grounding if context
        # includes query_type. Additional oracle queries can be made here.

        if grounding_result.is_grounded():
            logger.debug(f"Phase 0c: GROUND - oracle={grounding_result.oracle_id}, "
                         f"latency={grounding_result.oracle_latency_ms:.1f}ms")

        # =================================================================
        # PHASE 1: DETECT (PRISM Signal Extraction - Grounding-Aware)
        # =================================================================
        logger.debug("Phase 1: DETECT")

        # Check for ALL CAPS
        caps_detected = self.detector.detect_caps_anger(message)

        # Detect signals with FIXED priority order
        signals = self.detector.detect(message, context)

        logger.debug(f"  Signals: emotional={signals.emotional_score:.2f}, "
                     f"mode={signals.mode_detected}, task={signals.primary_task}")

        # =================================================================
        # PHASE 2: CASCADE (Expert Routing)
        # =================================================================
        logger.debug("Phase 2: CASCADE")

        # Detect task completion from signals (enables Celebrator expert)
        task_completed = signals.task_completed()

        routing = self.router.route(
            signals=signals,
            burnout=snapshot.burnout_level,
            energy=snapshot.energy_level,
            momentum=snapshot.momentum_phase,
            mode=snapshot.mode.value,
            tangent_budget=snapshot.tangent_budget,
            task_completed=task_completed,
            caps_detected=caps_detected,
            hallucination_score=grounding_result.hallucination_score  # v6.0.0
        )

        logger.debug(f"  Routing: expert={routing.expert.value}, "
                     f"trigger={routing.trigger}, "
                     f"safety_redirect={routing.safety_redirect}")

        # =================================================================
        # PHASE 3: LOCK (Parameter Locking)
        # =================================================================
        logger.debug("Phase 3: LOCK")

        lock = self.locker.lock(
            routing=routing,
            burnout=snapshot.burnout_level,
            energy=snapshot.energy_level,
            altitude=snapshot.altitude,
            requested_depth=requested_depth,
            mode=snapshot.mode.value,
            epistemic_tension=snapshot.epistemic_tension,
            reflection_count=snapshot.reflection_count,  # Batch-invariance: from snapshot
            source_mode=grounding_result.source_mode.value  # v6.0.0
        )

        logger.debug(f"  Lock: {lock.params.to_anchor()}, "
                     f"safety_capped={lock.safety_capped}")

        # =================================================================
        # PHASE 4: EXECUTE (handled externally by decision engine)
        # =================================================================
        # The orchestrator prepares params; execution happens in Claude's response

        # =================================================================
        # PHASE 5: UPDATE (Convergence Tracking)
        # =================================================================
        logger.debug("Phase 5: UPDATE")

        # Map locked params back to enums for convergence tracking
        paradigm = Paradigm.CORTEX if lock.params.paradigm == "Cortex" else Paradigm.MYCELIUM

        convergence = self.tracker.update(
            expert=routing.expert,
            paradigm=paradigm,
            burnout=snapshot.burnout_level,
            momentum=snapshot.momentum_phase,
            altitude=snapshot.altitude
        )

        logger.debug(f"  Convergence: xi={convergence.epistemic_tension:.3f}, "
                     f"attractor={convergence.attractor_basin.value}, "
                     f"stable={convergence.stable_exchanges}/3, "
                     f"converged={convergence.converged}")

        # =================================================================
        # STEP 6: COMMIT STATE CHANGES
        # =================================================================
        # Calculate new reflection_count (batch-invariance: update AFTER processing)
        new_reflection_count = snapshot.reflection_count + 1

        # Reset reflection count on early convergence
        if lock.converged:
            logger.info("Early convergence detected - resetting reflection count")
            new_reflection_count = 0

        state_updates = {
            "exchange_count": snapshot.exchange_count + 1,
            "reflection_count": new_reflection_count,  # Batch-invariance: increment after processing
            "convergence_attractor": convergence.attractor_basin.value,
            "epistemic_tension": convergence.epistemic_tension,
            "stable_exchanges": convergence.stable_exchanges
        }

        # Update mode based on signals
        if signals.mode_detected:
            mode_map = {
                "exploring": CognitiveMode.EXPLORING,
                "focused": CognitiveMode.FOCUSED,
                "teaching": CognitiveMode.TEACHING,
                "recovery": CognitiveMode.RECOVERY
            }
            if signals.mode_detected in mode_map:
                state_updates["mode"] = mode_map[signals.mode_detected]

        self.state_manager.batch_update(state_updates)

        # =================================================================
        # BUILD RESULT
        # =================================================================
        processing_time = (time.time() - start_time) * 1000

        result = NexusResult(
            grounding=grounding_result,  # v6.0.0: Phases 0b/0c
            signals=signals,
            routing=routing,
            lock=lock,
            convergence=convergence,
            processing_time_ms=processing_time,
            state_checksum=state_checksum
        )

        self._last_result = result

        logger.info(f"NEXUS Pipeline complete: {result.to_anchor()} ({processing_time:.1f}ms)")

        return result

    def get_last_result(self) -> Optional[NexusResult]:
        """Get the last processing result."""
        return self._last_result

    def get_state(self) -> CognitiveState:
        """Get current cognitive state."""
        return self.state_manager.get_state()

    def reset_session(self) -> None:
        """Reset session state (new task/session)."""
        self.locker.reset()
        self.tracker.reset()
        self.state_manager.reset()
        self.grounding.reset_budget()  # v6.0.0: Reset grounding budget
        self._last_result = None
        logger.info("Session reset")

    def calibrate(self, focus_level: str = None, urgency: str = None) -> None:
        """
        Calibrate cognitive state from non-invasive questions.

        Args:
            focus_level: 'scattered', 'moderate', or 'locked_in'
            urgency: 'relaxed', 'moderate', or 'deadline'
        """
        self.state_manager.calibrate(focus_level, urgency)

    def update_burnout(self, level: BurnoutLevel) -> None:
        """Update burnout level."""
        self.state_manager.batch_update({"burnout_level": level})

    def update_energy(self, level: EnergyLevel) -> None:
        """Update energy level."""
        self.state_manager.batch_update({"energy_level": level})

    def complete_task(self) -> None:
        """Record task completion."""
        state = self.state_manager.get_state()
        state.complete_task()
        self.state_manager.save()


# =============================================================================
# Factory Function
# =============================================================================

def create_orchestrator() -> CognitiveOrchestrator:
    """Create a CognitiveOrchestrator instance with default modules."""
    return CognitiveOrchestrator()


__all__ = [
    'NexusResult', 'CognitiveOrchestrator', 'create_orchestrator'
]
