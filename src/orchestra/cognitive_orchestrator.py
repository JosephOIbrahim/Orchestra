"""
Cognitive Orchestrator
======================

Ties together all cognitive modules in the 8-Phase NEXUS Pipeline.

Pipeline (v7.0.0):
0.  RETRIEVE  - Knowledge check for factual queries (fast path)
0b. CLASSIFY  - Determine source mode (LEARN|ACCESS|HYBRID)
0c. GROUND    - Query oracle if ACCESS/HYBRID mode
1.  DETECT    - PRISM signal extraction (grounding-aware)
2.  CASCADE   - Constitutional/safety gates + Cognitive Safety MoE + GROUNDING_MoE + BCM trail
3.  LOCK      - Parameter locking with MAX3 bounds + source_mode + BCM depth optimization
4.  EXECUTE   - Decision engine routing (work/delegate/protect)
5.  UPDATE    - RC^+xi convergence tracking + grounding metrics + BCM trail updates

ThinkingMachines [He2025] Compliance:
- State snapshot BEFORE processing (batch-invariance)
- FIXED evaluation order (8 phases, no reordering)
- FIXED signal priority (emotional > grounding > mode > domain > task)
- FIXED expert priority (Validator > ... > Direct, GROUNDING_MoE parallel)
- LOCKED parameters during generation
- Deterministic checksums
- Time-windowed oracle determinism
- v7.0.0: BCM trail updates QUEUED during processing, applied AFTER (batch-invariant)

Reference: [GWM2026] "Grounded World Models: Deterministic Physics Reasoning"
Core Thesis: "LLMs don't need to LEARN physics—they need ACCESS to physics"

v7.0.0: BCM Integration
- Trail loaded at pipeline start (lazy)
- Trail confidence passed as METADATA to routing/locking/convergence
- Trail NEVER affects selection ORDER (ThinkingMachines compliance)
- Outcome recording queued, flushed at session end

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
# v7.0.0: BCM Trail Integration
from .bcm_integration import BCMPipelineAdapter, create_adapter

logger = logging.getLogger(__name__)


# =============================================================================
# NEXUS Result
# =============================================================================

@dataclass
class NexusResult:
    """
    Complete result from the 8-Phase NEXUS Pipeline (v7.0.0).

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

    # v7.0.0: BCM Trail metadata (aggregated from all phases)
    bcm_trail_version: str = ""
    bcm_trail_enhanced: bool = False

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
            "state_checksum": self.state_checksum,

            # v7.0.0: BCM Trail metadata
            "bcm_trail_version": self.bcm_trail_version,
            "bcm_trail_enhanced": self.bcm_trail_enhanced,
            "bcm_routing_confidence": self.routing.bcm_confidence if self.routing else 1.0,
            "bcm_lock_optimized": self.lock.bcm_optimized if self.lock else False,
            "bcm_convergence_enhanced": self.convergence.bcm_enhanced if self.convergence else False
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
        grounding_bridge: Optional[GroundingBridge] = None,  # v6.0.0
        bcm_adapter: Optional[BCMPipelineAdapter] = None,  # v7.0.0
        session_id: str = "default"  # v7.0.0
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
            bcm_adapter: v7.0.0 - BCM trail adapter (creates default if None)
            session_id: v7.0.0 - Session ID for BCM trail persistence
        """
        self.state_manager = state_manager or CognitiveStateManager()
        self.detector = detector or create_detector()
        self.router = router or create_router()
        self.locker = locker or create_locker()
        self.tracker = tracker or create_tracker()
        self.grounding = grounding_bridge or create_grounding_bridge()  # v6.0.0
        self.bcm = bcm_adapter or create_adapter(session_id, load=True)  # v7.0.0

        self._last_result: Optional[NexusResult] = None
        # v7.0.0: Pending signal fingerprints for BCM reliability tracking
        self._pending_signal_fingerprints: list = []

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
        # STEP 0a (v7.0.0): LOAD BCM TRAIL (Lazy loading)
        # =================================================================
        trail = self.bcm.ensure_loaded()
        logger.debug(f"BCM trail loaded: version={trail.version if trail else 'none'}")

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

        # v7.0.0: Capture signal fingerprint for BCM reliability tracking
        # Batch-invariance: fingerprint captured but NOT used during processing
        signal_fingerprint = signals.get_signal_fingerprint()
        self._pending_signal_fingerprints.append(signal_fingerprint)

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
            hallucination_score=grounding_result.hallucination_score,  # v6.0.0
            trail=trail  # v7.0.0: BCM trail for confidence metadata
        )

        logger.debug(f"  Routing: expert={routing.expert.value}, "
                     f"trigger={routing.trigger}, "
                     f"safety_redirect={routing.safety_redirect}")

        # =================================================================
        # PHASE 3: LOCK (Parameter Locking)
        # =================================================================
        logger.debug("Phase 3: LOCK")

        # Determine task type from signals for BCM depth optimization
        task_type = signals.primary_task if signals else ""

        lock = self.locker.lock(
            routing=routing,
            burnout=snapshot.burnout_level,
            energy=snapshot.energy_level,
            altitude=snapshot.altitude,
            requested_depth=requested_depth,
            mode=snapshot.mode.value,
            epistemic_tension=snapshot.epistemic_tension,
            reflection_count=snapshot.reflection_count,  # Batch-invariance: from snapshot
            source_mode=grounding_result.source_mode.value,  # v6.0.0
            trail=trail,  # v7.0.0: BCM trail for depth optimization
            task_type=task_type  # v7.0.0: Task type for depth history lookup
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
            altitude=snapshot.altitude,
            trail=trail  # v7.0.0: BCM trail for attractor preferences
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
            "stable_exchanges": convergence.stable_exchanges,
            # v7.0.0: BCM trail state
            "bcm_trail_version": trail.version if trail else "",
            "bcm_expert_confidence": self.bcm.get_all_expert_confidences(),
            "bcm_plasticity_active": self.bcm.is_plasticity_active(),
            "bcm_last_update": trail.last_update if trail else 0.0
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
        # STEP 6c: PLASTICITY AUTO-TRIGGERS (v7.0.0)
        # =================================================================
        # Determinism: Same state → same trigger decision
        # Plasticity affects learning rate, NOT routing (ThinkingMachines compliance)

        plasticity_active = self.bcm.is_plasticity_active()

        # Auto-OPEN on crash + ORANGE conditions
        if (snapshot.momentum_phase == MomentumPhase.CRASHED and
            snapshot.burnout_level == BurnoutLevel.ORANGE and
            not plasticity_active):
            self.open_plasticity_window(
                "auto_crash_recovery",
                divergence=min(1.0, convergence.epistemic_tension * 2)
            )
            logger.info("Auto-opened plasticity window: crash + ORANGE condition")

        # Auto-OPEN on RED burnout (emergency learning mode)
        elif (snapshot.burnout_level == BurnoutLevel.RED and
              not plasticity_active):
            self.open_plasticity_window("auto_red_burnout", divergence=1.0)
            logger.info("Auto-opened plasticity window: RED burnout condition")

        # Auto-CLOSE on stable convergence (3+ stable exchanges)
        elif (convergence.converged and
              plasticity_active and
              convergence.stable_exchanges >= 3):
            self.close_plasticity_window()
            logger.info("Auto-closed plasticity window: stable convergence achieved")

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
            state_checksum=state_checksum,
            # v7.0.0: BCM Trail metadata
            bcm_trail_version=trail.version if trail else "",
            bcm_trail_enhanced=routing.bcm_enhanced if routing else False
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
        # v7.0.0: Flush and save BCM trail before reset
        updates, saved = self.bcm.flush_and_save()
        if updates > 0:
            logger.info(f"BCM trail: {updates} updates flushed, saved={saved}")
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

    # =========================================================================
    # v7.0.0: BCM Trail Methods
    # =========================================================================

    def record_outcome(
        self,
        success: bool,
        latency_ms: float = 0.0,
        task_type: str = "",
        depth: str = ""
    ) -> None:
        """
        Record outcome for BCM trail learning.

        v7.0.0: Queue outcome for batch update (ThinkingMachines compliance).
        Updates are applied on session end or explicit flush.

        Args:
            success: Whether the routing was successful
            latency_ms: Response latency
            task_type: Task type
            depth: Thinking depth used
        """
        if self._last_result and self._last_result.routing:
            expert = self._last_result.routing.expert.value
            self.bcm.record_expert_outcome(
                expert=expert,
                success=success,
                latency_ms=latency_ms,
                task_type=task_type,
                depth=depth
            )

            # Also record convergence outcome
            if self._last_result.convergence:
                attractor = self._last_result.convergence.attractor_basin.value
                self.bcm.record_attractor_outcome(
                    attractor=attractor,
                    converged=self._last_result.convergence.converged
                )

            # v7.0.0: Record signal outcomes for reliability tracking
            signal_count = 0
            for fingerprint in self._pending_signal_fingerprints:
                # Record each signal category separately
                for category, signal_name in fingerprint.items():
                    self.bcm.record_signal_outcome(
                        category=category,
                        signal_name=signal_name,
                        correct=success
                    )
                    signal_count += 1

            # Clear pending fingerprints after recording
            self._pending_signal_fingerprints.clear()

            logger.debug(f"BCM outcome recorded: expert={expert}, success={success}, "
                         f"signals={signal_count}")

    def flush_bcm_trail(self) -> tuple[int, bool]:
        """
        Flush queued BCM updates and save trail.

        v7.0.0: Apply all queued updates to trail and persist.

        Returns:
            Tuple of (updates_applied, save_successful)
        """
        return self.bcm.flush_and_save()

    def get_bcm_trail(self):
        """Get the BCM trail (for inspection/debugging)."""
        return self.bcm.get_trail()

    def open_plasticity_window(self, trigger: str, divergence: float = 0.5) -> None:
        """
        Open BCM plasticity window (e.g., after crash).

        v7.0.0: Boosts learning rate for trail updates.

        Args:
            trigger: What triggered the window (e.g., "crashed", "red_burnout")
            divergence: Divergence level (0.0-1.0)
        """
        self.bcm.open_plasticity_window(trigger, divergence)
        logger.info(f"BCM plasticity window opened: trigger={trigger}, divergence={divergence}")

    def close_plasticity_window(self) -> None:
        """Close BCM plasticity window."""
        self.bcm.close_plasticity_window()
        logger.info("BCM plasticity window closed")


# =============================================================================
# Factory Function
# =============================================================================

def create_orchestrator() -> CognitiveOrchestrator:
    """Create a CognitiveOrchestrator instance with default modules."""
    return CognitiveOrchestrator()


__all__ = [
    'NexusResult', 'CognitiveOrchestrator', 'create_orchestrator'
]
