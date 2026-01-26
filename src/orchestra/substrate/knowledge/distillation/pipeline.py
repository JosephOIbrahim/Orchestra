"""
Distillation Pipeline

Main orchestrator for the knowledge distillation process.
Coordinates all stages: ingest -> query -> answer -> extract -> validate -> write.

Part of USD Cognitive Substrate - Knowledge Prims Distillation.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import logging
import sys
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from ..schemas import KnowledgePrim
from .answer_generator import AnswerGenerator, GeneratedAnswer
from .benchmark import Benchmark, BenchmarkResult
from .checkpoint import (
    CheckpointManager,
    PipelineStage,
    create_checkpoint_manager,
)
from .confidence_scorer import ConfidenceScorer
from .config import DistillationConfig
from .corpus_ingester import CorpusIngester, DocumentChunk
from .llm_client import BaseLLMClient, create_llm_client
from .prim_extractor import ExtractionResult, PrimExtractor
from .query_generator import GeneratedQuery, QueryGenerator
from .trigger_generator import TriggerGenerator
from .usda_writer import USDAWriter
from .validator import ValidationResult, Validator

logger = logging.getLogger(__name__)


@dataclass
class PipelineStats:
    """Statistics from pipeline execution.

    Attributes:
        started_at: When pipeline started
        completed_at: When pipeline completed
        documents_processed: Number of documents ingested
        chunks_generated: Number of chunks created
        queries_generated: Number of queries generated
        answers_generated: Number of answers generated
        prims_extracted: Number of prims extracted
        prims_passed_validation: Number passing validation
        prims_written: Number written to files
        benchmark_result: Optional benchmark result
        output_files: List of output file paths
        deterministic_checksum: Content-addressable checksum excluding timestamps
        prim_content_hashes: Sorted list of prim content hashes for verification
    """
    started_at: str = ""
    completed_at: str = ""
    documents_processed: int = 0
    chunks_generated: int = 0
    queries_generated: int = 0
    answers_generated: int = 0
    prims_extracted: int = 0
    prims_passed_validation: int = 0
    prims_written: int = 0
    benchmark_result: BenchmarkResult | None = None
    output_files: list[str] = field(default_factory=list)
    deterministic_checksum: str = ""
    prim_content_hashes: list[str] = field(default_factory=list)

    def compute_deterministic_checksum(self, prims: list[KnowledgePrim] | None = None) -> str:
        """Compute content-addressable checksum excluding timestamps.

        ThinkingMachines [He2025] batch-invariance compliant:
        Same inputs → Same checksum regardless of execution timing.

        Args:
            prims: Optional list of prims to include in checksum

        Returns:
            SHA-256 checksum (64 chars)
        """
        # Build deterministic data string (excludes timestamps)
        data_parts = [
            f"docs:{self.documents_processed}",
            f"chunks:{self.chunks_generated}",
            f"queries:{self.queries_generated}",
            f"answers:{self.answers_generated}",
            f"extracted:{self.prims_extracted}",
            f"passed:{self.prims_passed_validation}",
            f"written:{self.prims_written}",
        ]

        # Add sorted prim content hashes if available
        if prims:
            prim_hashes = []
            for prim in prims:
                # Hash each prim's essential content
                prim_data = f"{prim.canonical_path}:{prim.content}:{prim.summary}"
                prim_hash = hashlib.sha256(prim_data.encode()).hexdigest()[:16]
                prim_hashes.append(prim_hash)
            # Sort for determinism
            prim_hashes.sort()
            self.prim_content_hashes = prim_hashes
            data_parts.append(f"prims:{','.join(prim_hashes)}")

        data = "|".join(data_parts)
        self.deterministic_checksum = hashlib.sha256(data.encode()).hexdigest()
        return self.deterministic_checksum

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "documents_processed": self.documents_processed,
            "chunks_generated": self.chunks_generated,
            "queries_generated": self.queries_generated,
            "answers_generated": self.answers_generated,
            "prims_extracted": self.prims_extracted,
            "prims_passed_validation": self.prims_passed_validation,
            "prims_written": self.prims_written,
            "validation_pass_rate": (
                self.prims_passed_validation / self.prims_extracted
                if self.prims_extracted > 0 else 0.0
            ),
            "benchmark": self.benchmark_result.to_dict() if self.benchmark_result else None,
            "output_files": self.output_files,
            "deterministic_checksum": self.deterministic_checksum,
        }


class DistillationPipeline:
    """Orchestrates the complete knowledge distillation process.

    Pipeline stages:
    1. Corpus Ingestion - Read and chunk documents
    2. Query Generation - Generate questions from chunks
    3. Answer Generation - Generate answers with reasoning
    4. Prim Extraction - Convert to KnowledgePrim format
    5. Trigger Generation - Auto-generate search triggers
    6. Validation - Check for hallucination and accuracy
    7. Confidence Scoring - Assign confidence scores
    8. USDA Writing - Output to .usda files
    9. Benchmarking - Test hypothesis (optional)

    Supports checkpointing for resumability after failures.
    ThinkingMachines [He2025] Production Hardening compliant.

    Attributes:
        config: Pipeline configuration
    """

    def __init__(self, config: DistillationConfig) -> None:
        self.config = config
        self._llm_client: BaseLLMClient | None = None
        self._stats = PipelineStats()
        self._checkpoint_manager: CheckpointManager | None = None

    def _get_config_hash(self) -> str:
        """Compute hash of configuration for checkpoint compatibility.

        Returns:
            SHA-256 hash of config (16 chars)
        """
        config_data = json.dumps({
            "model_name": self.config.model_name,
            "chunk_size": self.config.chunk_size,
            "chunk_overlap": self.config.chunk_overlap,
            "queries_per_document": self.config.queries_per_document,
            "thresholds": self.config.effective_thresholds,
        }, sort_keys=True)
        return hashlib.sha256(config_data.encode()).hexdigest()[:16]

    def _get_llm_client(self) -> BaseLLMClient:
        """Get or create LLM client."""
        if self._llm_client is None:
            self._llm_client = create_llm_client(self.config)
        return self._llm_client

    async def run(
        self,
        corpus_dir: Path | None = None,
        output_dir: Path | None = None,
        run_benchmark: bool = True,
        resume: bool = True,
    ) -> PipelineStats:
        """Run the complete distillation pipeline.

        Supports checkpointing for resumability. If a previous run was
        interrupted, it will resume from the last completed stage.

        Args:
            corpus_dir: Override config corpus directory
            output_dir: Override config output directory
            run_benchmark: Whether to run benchmark after distillation
            resume: Whether to resume from checkpoint if available

        Returns:
            PipelineStats with execution metrics
        """
        self._stats = PipelineStats()
        self._stats.started_at = datetime.now().isoformat()

        # Override config paths if provided
        if corpus_dir:
            self.config.corpus_dir = corpus_dir
        if output_dir:
            self.config.output_dir = output_dir

        self.config.ensure_directories()

        # Initialize checkpoint manager
        checkpoint_dir = self.config.checkpoint_dir or (self.config.output_dir / ".checkpoints")
        self._checkpoint_manager = create_checkpoint_manager(
            checkpoint_dir.parent,
            enabled=self.config.enable_checkpointing,
        )

        # Check for existing checkpoint
        existing_checkpoint = None
        resume_stage = None
        if resume and self.config.enable_checkpointing:
            existing_checkpoint = self._checkpoint_manager.load_checkpoint()
            if existing_checkpoint:
                # Validate config compatibility
                config_hash = self._get_config_hash()
                if existing_checkpoint.config_hash != config_hash:
                    logger.warning(
                        "Config changed since checkpoint - starting fresh. "
                        f"Old hash: {existing_checkpoint.config_hash}, "
                        f"New hash: {config_hash}"
                    )
                    self._checkpoint_manager.clear()
                    existing_checkpoint = None
                else:
                    resume_stage = self._checkpoint_manager.get_resume_stage()
                    if resume_stage:
                        logger.info(f"Resuming from stage: {resume_stage.value}")

        # Initialize new checkpoint if needed
        if not existing_checkpoint:
            run_id = str(uuid.uuid4())[:8]
            self._checkpoint_manager.initialize(
                run_id=run_id,
                config_hash=self._get_config_hash(),
                corpus_dir=self.config.corpus_dir,
                output_dir=self.config.output_dir,
            )

        try:
            # Stage 1: Ingest corpus
            if resume_stage and resume_stage.value > PipelineStage.INGESTED.value:
                logger.info("Stage 1: Loading ingested data from checkpoint...")
                chunks = self._load_chunks_from_checkpoint()
            else:
                logger.info("Stage 1: Ingesting corpus...")
                chunks = await self._stage_ingest()
                self._save_stage_checkpoint(
                    PipelineStage.INGESTED,
                    chunks,
                    {"documents": self._stats.documents_processed},
                )

            # Stage 2: Generate queries
            if resume_stage and self._stage_index(resume_stage) > self._stage_index(PipelineStage.QUERIES_GENERATED):
                logger.info("Stage 2: Loading queries from checkpoint...")
                queries_with_chunks = self._load_queries_from_checkpoint(chunks)
            else:
                logger.info("Stage 2: Generating queries...")
                queries_with_chunks = await self._stage_generate_queries(chunks)
                self._save_stage_checkpoint(
                    PipelineStage.QUERIES_GENERATED,
                    queries_with_chunks,
                    {"count": len(queries_with_chunks)},
                )

            # Stage 3: Generate answers
            if resume_stage and self._stage_index(resume_stage) > self._stage_index(PipelineStage.ANSWERS_GENERATED):
                logger.info("Stage 3: Loading answers from checkpoint...")
                answers = self._load_answers_from_checkpoint()
            else:
                logger.info("Stage 3: Generating answers...")
                answers = await self._stage_generate_answers(queries_with_chunks)
                self._save_stage_checkpoint(
                    PipelineStage.ANSWERS_GENERATED,
                    answers,
                    {"count": len(answers)},
                )

            # Stage 4: Extract prims
            if resume_stage and self._stage_index(resume_stage) > self._stage_index(PipelineStage.PRIMS_EXTRACTED):
                logger.info("Stage 4: Loading prims from checkpoint...")
                extraction_results = self._load_extractions_from_checkpoint()
            else:
                logger.info("Stage 4: Extracting prims...")
                extraction_results = await self._stage_extract_prims(answers)
                self._save_stage_checkpoint(
                    PipelineStage.PRIMS_EXTRACTED,
                    extraction_results,
                    {"count": len(extraction_results)},
                )

            # Get just the prims
            prims = [r.prim for r in extraction_results]

            # Stage 5: Generate triggers
            if resume_stage and self._stage_index(resume_stage) > self._stage_index(PipelineStage.TRIGGERS_GENERATED):
                logger.info("Stage 5: Loading triggered prims from checkpoint...")
                prims = self._load_prims_from_checkpoint(PipelineStage.TRIGGERS_GENERATED)
            else:
                logger.info("Stage 5: Generating triggers...")
                prims = await self._stage_generate_triggers(prims)
                self._save_stage_checkpoint(
                    PipelineStage.TRIGGERS_GENERATED,
                    prims,
                    {"count": len(prims)},
                )

            # Stage 6: Validate
            if resume_stage and self._stage_index(resume_stage) > self._stage_index(PipelineStage.VALIDATED):
                logger.info("Stage 6: Loading validation from checkpoint...")
                validation_results = self._load_validation_from_checkpoint()
                prim_answer_map = self._build_prim_answer_map(extraction_results)
            else:
                logger.info("Stage 6: Running verification...")
                validation_results, prim_answer_map = await self._stage_check(
                    prims, extraction_results
                )
                self._save_stage_checkpoint(
                    PipelineStage.VALIDATED,
                    validation_results,
                    {"passed": sum(1 for r in validation_results if r.passed)},
                )

            # Stage 7: Score confidence
            if resume_stage and self._stage_index(resume_stage) > self._stage_index(PipelineStage.SCORED):
                logger.info("Stage 7: Loading scored prims from checkpoint...")
                prims = self._load_prims_from_checkpoint(PipelineStage.SCORED)
            else:
                logger.info("Stage 7: Scoring confidence...")
                prims = await self._stage_score(prims, validation_results, prim_answer_map)
                self._save_stage_checkpoint(
                    PipelineStage.SCORED,
                    prims,
                    {"count": len(prims)},
                )

            # Filter to passing prims only
            passing_prims = self._filter_passing(prims, validation_results)
            self._stats.prims_passed_validation = len(passing_prims)

            # Stage 8: Write USDA
            if resume_stage and self._stage_index(resume_stage) > self._stage_index(PipelineStage.WRITTEN):
                logger.info("Stage 8: Loading output paths from checkpoint...")
                output_paths = self._load_output_paths_from_checkpoint()
            else:
                logger.info("Stage 8: Writing USDA files...")
                output_paths = await self._stage_write(passing_prims)
                self._save_stage_checkpoint(
                    PipelineStage.WRITTEN,
                    [str(p) for p in output_paths],
                    {"count": len(output_paths)},
                )
            self._stats.output_files = [str(p) for p in output_paths]

            # Stage 9: Benchmark (optional)
            if run_benchmark and passing_prims:
                logger.info("Stage 9: Running benchmark...")
                self._stats.benchmark_result = await self._stage_benchmark(passing_prims)
                self._checkpoint_manager.save_stage(
                    PipelineStage.BENCHMARKED,
                    item_count=1,
                    metadata={"speedup": self._stats.benchmark_result.speedup_ratio if self._stats.benchmark_result else 0},
                )

            # Mark pipeline complete
            self._checkpoint_manager.save_stage(
                PipelineStage.COMPLETED,
                item_count=self._stats.prims_written,
            )

            # Compute deterministic checksum (ThinkingMachines [He2025])
            self._stats.compute_deterministic_checksum(passing_prims)
            logger.info(f"Deterministic checksum: {self._stats.deterministic_checksum[:16]}...")

        except Exception as e:
            logger.error(f"Pipeline failed: {e}", exc_info=True)
            raise

        self._stats.completed_at = datetime.now().isoformat()

        # Log summary
        logger.info(self._format_summary())

        return self._stats

    def _stage_index(self, stage: PipelineStage) -> int:
        """Get numeric index of a pipeline stage for comparison.

        Args:
            stage: Pipeline stage

        Returns:
            Index in STAGE_ORDER (0-based)
        """
        from .checkpoint import STAGE_ORDER
        try:
            return STAGE_ORDER.index(stage)
        except ValueError:
            return -1

    def _save_stage_checkpoint(
        self,
        stage: PipelineStage,
        data: Any,
        metadata: dict[str, Any],
    ) -> None:
        """Save checkpoint for a completed stage.

        Args:
            stage: Completed stage
            data: Data to serialize for resumption
            metadata: Stage metadata
        """
        if not self._checkpoint_manager:
            return

        # Serialize data based on type
        serialized = self._serialize_stage_data(stage, data)

        item_count = metadata.get("count", len(data) if hasattr(data, "__len__") else 0)
        self._checkpoint_manager.save_stage(
            stage,
            item_count=item_count,
            data=serialized,
            metadata=metadata,
        )

    def _serialize_stage_data(self, stage: PipelineStage, data: Any) -> Any:
        """Serialize stage data for checkpoint storage.

        Args:
            stage: Pipeline stage
            data: Data to serialize

        Returns:
            JSON-serializable representation
        """
        if stage == PipelineStage.INGESTED:
            # DocumentChunk list
            return [
                {
                    "chunk_id": c.chunk_id,
                    "content": c.content,
                    "source_path": str(c.source_path),
                    "chunk_index": c.chunk_index,
                    "word_count": c.word_count,
                    "metadata": c.metadata,
                }
                for c in data
            ]

        elif stage == PipelineStage.QUERIES_GENERATED:
            # List of (GeneratedQuery, DocumentChunk) tuples
            return [
                {
                    "query": q.to_dict(),
                    "chunk_id": c.chunk_id,
                }
                for q, c in data
            ]

        elif stage == PipelineStage.ANSWERS_GENERATED:
            # List of GeneratedAnswer
            return [a.to_dict() for a in data]

        elif stage == PipelineStage.PRIMS_EXTRACTED:
            # List of ExtractionResult
            return [
                {
                    "prim": r.prim.to_dict() if hasattr(r.prim, "to_dict") else self._prim_to_dict(r.prim),
                    "answer": r.answer.to_dict() if r.answer else None,
                    "extraction_path": r.extraction_path,
                }
                for r in data
            ]

        elif stage in (PipelineStage.TRIGGERS_GENERATED, PipelineStage.SCORED):
            # List of KnowledgePrim
            return [
                self._prim_to_dict(p) if not hasattr(p, "to_dict") else p.to_dict()
                for p in data
            ]

        elif stage == PipelineStage.VALIDATED:
            # List of ValidationResult
            return [r.to_dict() for r in data]

        elif stage == PipelineStage.WRITTEN:
            # List of path strings
            return data

        return data

    def _prim_to_dict(self, prim: KnowledgePrim) -> dict[str, Any]:
        """Convert KnowledgePrim to dictionary.

        Args:
            prim: Knowledge prim

        Returns:
            Dictionary representation
        """
        return {
            "canonical_path": prim.canonical_path,
            "content": prim.content,
            "summary": prim.summary,
            "confidence": prim.confidence,
            "provenance": prim.provenance,
            "domains": prim.domains,
            "triggers": prim.triggers,
            "requires": prim.requires,
            "enables": prim.enables,
            "related_to": prim.related_to,
            "teaching_altitude": prim.teaching_altitude,
            "key_concepts": prim.key_concepts,
        }

    def _load_chunks_from_checkpoint(self) -> list[DocumentChunk]:
        """Load chunks from checkpoint."""
        data = self._checkpoint_manager.load_stage_data(PipelineStage.INGESTED)
        if not data:
            raise ValueError("No chunk data in checkpoint")

        chunks = []
        for item in data:
            chunk = DocumentChunk(
                chunk_id=item["chunk_id"],
                content=item["content"],
                source_path=Path(item["source_path"]),
                chunk_index=item["chunk_index"],
                word_count=item["word_count"],
                metadata=item.get("metadata", {}),
            )
            chunks.append(chunk)

        self._stats.chunks_generated = len(chunks)
        return chunks

    def _load_queries_from_checkpoint(
        self, chunks: list[DocumentChunk]
    ) -> list[tuple[GeneratedQuery, DocumentChunk]]:
        """Load queries from checkpoint."""
        data = self._checkpoint_manager.load_stage_data(PipelineStage.QUERIES_GENERATED)
        if not data:
            raise ValueError("No query data in checkpoint")

        # Build chunk lookup
        chunk_map = {c.chunk_id: c for c in chunks}

        pairs = []
        for item in data:
            query = GeneratedQuery.from_dict(item["query"])
            chunk = chunk_map.get(item["chunk_id"])
            if chunk:
                pairs.append((query, chunk))

        self._stats.queries_generated = len(pairs)
        return pairs

    def _load_answers_from_checkpoint(self) -> list[GeneratedAnswer]:
        """Load answers from checkpoint."""
        data = self._checkpoint_manager.load_stage_data(PipelineStage.ANSWERS_GENERATED)
        if not data:
            raise ValueError("No answer data in checkpoint")

        answers = [GeneratedAnswer.from_dict(item) for item in data]
        self._stats.answers_generated = len(answers)
        return answers

    def _load_extractions_from_checkpoint(self) -> list[ExtractionResult]:
        """Load extraction results from checkpoint."""
        data = self._checkpoint_manager.load_stage_data(PipelineStage.PRIMS_EXTRACTED)
        if not data:
            raise ValueError("No extraction data in checkpoint")

        results = []
        for item in data:
            prim = self._dict_to_prim(item["prim"])
            answer = GeneratedAnswer.from_dict(item["answer"]) if item.get("answer") else None
            result = ExtractionResult(
                prim=prim,
                answer=answer,
                extraction_path=item.get("extraction_path", ""),
            )
            results.append(result)

        self._stats.prims_extracted = len(results)
        return results

    def _load_prims_from_checkpoint(self, stage: PipelineStage) -> list[KnowledgePrim]:
        """Load prims from checkpoint."""
        data = self._checkpoint_manager.load_stage_data(stage)
        if not data:
            raise ValueError(f"No prim data in checkpoint for {stage.value}")

        return [self._dict_to_prim(item) for item in data]

    def _load_validation_from_checkpoint(self) -> list[ValidationResult]:
        """Load validation results from checkpoint."""
        data = self._checkpoint_manager.load_stage_data(PipelineStage.VALIDATED)
        if not data:
            raise ValueError("No validation data in checkpoint")

        results = []
        for item in data:
            result = ValidationResult(
                prim_path=item["prim_path"],
                retrieval_accuracy=item.get("retrieval_accuracy", 0.0),
                hallucination_score=item.get("hallucination_score", 1.0),
                consistency_score=item.get("consistency_score", 0.0),
                passed=item.get("passed", False),
                failure_reasons=item.get("failure_reasons", []),
                warnings=item.get("warnings", []),
                metadata=item.get("metadata", {}),
            )
            results.append(result)

        return results

    def _load_output_paths_from_checkpoint(self) -> list[Path]:
        """Load output paths from checkpoint."""
        data = self._checkpoint_manager.load_stage_data(PipelineStage.WRITTEN)
        if not data:
            return []

        return [Path(p) for p in data]

    def _dict_to_prim(self, data: dict[str, Any]) -> KnowledgePrim:
        """Convert dictionary to KnowledgePrim."""
        return KnowledgePrim(
            canonical_path=data.get("canonical_path", ""),
            content=data.get("content", ""),
            summary=data.get("summary", ""),
            confidence=data.get("confidence", 0.0),
            provenance=data.get("provenance", ""),
            domains=data.get("domains", []),
            triggers=data.get("triggers", []),
            requires=data.get("requires", []),
            enables=data.get("enables", []),
            related_to=data.get("related_to", []),
            teaching_altitude=data.get("teaching_altitude", "ground"),
            key_concepts=data.get("key_concepts", []),
        )

    def _build_prim_answer_map(
        self, extraction_results: list[ExtractionResult]
    ) -> dict[str, GeneratedAnswer]:
        """Build prim path to answer mapping."""
        return {
            r.prim.canonical_path: r.answer
            for r in extraction_results
            if r.answer
        }

    async def _stage_ingest(self) -> list[DocumentChunk]:
        """Stage 1: Ingest corpus."""
        ingester = CorpusIngester(self.config)
        chunks = list(ingester.ingest())

        self._stats.documents_processed = ingester.stats["documents_processed"]
        self._stats.chunks_generated = len(chunks)

        logger.info(
            f"Ingested {self._stats.documents_processed} documents, "
            f"{len(chunks)} chunks"
        )

        return chunks

    async def _stage_generate_queries(
        self, chunks: list[DocumentChunk]
    ) -> list[tuple[GeneratedQuery, DocumentChunk]]:
        """Stage 2: Generate queries from chunks."""
        generator = QueryGenerator(self.config, self._get_llm_client())

        query_chunk_pairs = []
        for chunk in chunks:
            queries = await generator.generate_queries(chunk)
            for query in queries:
                query_chunk_pairs.append((query, chunk))

        self._stats.queries_generated = len(query_chunk_pairs)

        logger.info(f"Generated {len(query_chunk_pairs)} queries")

        return query_chunk_pairs

    async def _stage_generate_answers(
        self, query_chunk_pairs: list[tuple[GeneratedQuery, DocumentChunk]]
    ) -> list[GeneratedAnswer]:
        """Stage 3: Generate answers."""
        generator = AnswerGenerator(self.config, self._get_llm_client())

        answers = await generator.generate_batch(query_chunk_pairs)

        self._stats.answers_generated = len(answers)

        logger.info(f"Generated {len(answers)} answers")

        return answers

    async def _stage_extract_prims(
        self, answers: list[GeneratedAnswer]
    ) -> list[ExtractionResult]:
        """Stage 4: Extract prims from answers."""
        extractor = PrimExtractor(self.config)

        results = extractor.extract_batch(answers)

        self._stats.prims_extracted = len(results)

        logger.info(f"Extracted {len(results)} prims")

        return results

    async def _stage_generate_triggers(
        self, prims: list[KnowledgePrim]
    ) -> list[KnowledgePrim]:
        """Stage 5: Generate and enhance triggers."""
        generator = TriggerGenerator(self.config, self._get_llm_client())

        enhanced = await generator.enhance_prims(prims)

        logger.info(f"Enhanced {len(enhanced)} prims with triggers")

        return enhanced

    async def _stage_check(
        self,
        prims: list[KnowledgePrim],
        extraction_results: list[ExtractionResult],
    ) -> tuple[list[ValidationResult], dict[str, GeneratedAnswer]]:
        """Stage 6: Run verification checks."""
        checker = Validator(self.config, self._get_llm_client())

        # Build prim -> answer mapping
        prim_answer_map = {}
        for result in extraction_results:
            prim_answer_map[result.prim.canonical_path] = result.answer

        # Check each prim
        pairs = [
            (prim, prim_answer_map.get(prim.canonical_path, GeneratedAnswer(answer="", summary="")))
            for prim in prims
        ]

        results = await checker.validate_batch(pairs)

        passed = sum(1 for r in results if r.passed)
        logger.info(f"Verification: {passed}/{len(results)} passed")

        return results, prim_answer_map

    async def _stage_score(
        self,
        prims: list[KnowledgePrim],
        check_results: list[ValidationResult],
        prim_answer_map: dict[str, GeneratedAnswer],
    ) -> list[KnowledgePrim]:
        """Stage 7: Calculate confidence scores."""
        scorer = ConfidenceScorer(self.config)

        # Build scoring tuples
        scoring_data = []
        for prim, check_result in zip(prims, check_results):
            answer = prim_answer_map.get(prim.canonical_path)
            source_conf = answer.confidence_hint if answer else 0.0
            scoring_data.append((prim, check_result, source_conf))

        breakdowns = scorer.score_batch(scoring_data)

        # Apply scores to prims
        scored_prims = scorer.apply_scores_to_prims(prims, breakdowns)

        return scored_prims

    def _filter_passing(
        self,
        prims: list[KnowledgePrim],
        check_results: list[ValidationResult],
    ) -> list[KnowledgePrim]:
        """Filter to only prims that passed checks."""
        result_lookup = {r.prim_path: r.passed for r in check_results}

        passing = [
            prim for prim in prims
            if result_lookup.get(prim.canonical_path, False)
        ]

        return passing

    async def _stage_write(
        self, prims: list[KnowledgePrim]
    ) -> list[Path]:
        """Stage 8: Write prims to USDA files."""
        writer = USDAWriter(self.config)

        # Group by domain for separate files
        domain_groups: dict[str, list[KnowledgePrim]] = {}
        for prim in prims:
            domain = prim.domains[0] if prim.domains else "general"
            if domain not in domain_groups:
                domain_groups[domain] = []
            domain_groups[domain].append(prim)

        paths = writer.write_batch(domain_groups)

        self._stats.prims_written = len(prims)

        return paths

    async def _stage_benchmark(
        self, prims: list[KnowledgePrim]
    ) -> BenchmarkResult:
        """Stage 9: Run hypothesis benchmark."""
        from ..retriever import KnowledgeRetriever

        # Create a temporary retriever with the new prims
        # For now, just do a quick benchmark
        benchmark = Benchmark(
            self.config,
            llm_client=self._get_llm_client(),
        )

        result = await benchmark.run(prims=prims, iterations=20)

        logger.info(result.summary())

        return result

    def _format_summary(self) -> str:
        """Format execution summary."""
        return f"""
Pipeline Complete
{'=' * 50}
Documents:    {self._stats.documents_processed}
Chunks:       {self._stats.chunks_generated}
Queries:      {self._stats.queries_generated}
Answers:      {self._stats.answers_generated}
Prims:        {self._stats.prims_extracted}
Passed:       {self._stats.prims_passed_validation}
Written:      {self._stats.prims_written}
Output files: {len(self._stats.output_files)}
"""


async def main():
    """CLI entry point for the pipeline."""
    parser = argparse.ArgumentParser(
        description="Knowledge Distillation Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--corpus",
        type=Path,
        required=True,
        help="Path to corpus directory",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path.home() / ".orchestra" / "knowledge" / "distilled",
        help="Output directory for USDA files",
    )
    parser.add_argument(
        "--model",
        type=str,
        default="claude-sonnet-4-20250514",
        help="LLM model to use",
    )
    parser.add_argument(
        "--queries-per-doc",
        type=int,
        default=5,
        help="Questions to generate per document chunk",
    )
    parser.add_argument(
        "--skip-benchmark",
        action="store_true",
        help="Skip benchmark after distillation",
    )
    parser.add_argument(
        "--no-resume",
        action="store_true",
        help="Don't resume from checkpoint, start fresh",
    )
    parser.add_argument(
        "--no-checkpoint",
        action="store_true",
        help="Disable checkpointing entirely",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose logging",
    )

    args = parser.parse_args()

    # Configure logging
    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    # Build config
    config = DistillationConfig(
        corpus_dir=args.corpus,
        output_dir=args.output,
        model_name=args.model,
        queries_per_document=args.queries_per_doc,
        enable_checkpointing=not args.no_checkpoint,
    )

    # Run pipeline
    pipeline = DistillationPipeline(config)
    stats = await pipeline.run(
        run_benchmark=not args.skip_benchmark,
        resume=not args.no_resume,
    )

    # Output stats as JSON
    print(json.dumps(stats.to_dict(), indent=2))

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
