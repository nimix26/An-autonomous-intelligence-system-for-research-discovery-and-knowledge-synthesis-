"""
Research Paper Discovery & Summarization Pipeline
"""

import argparse
import logging
import json
import sys
import asyncio

from pipelines.discovery_pipeline import DiscoveryPipeline


def setup_logging(level: str = "INFO"):
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[logging.StreamHandler(sys.stdout), logging.FileHandler("pipeline.log", encoding="utf-8")]
    )


async def _run(args):
    pipeline = DiscoveryPipeline()
    results = await pipeline.run(
        topic=args.topic,
        context=args.context,
        top_n=args.top_n,
        use_llm_relevance=not args.no_llm_scoring,
        summarize=not args.no_summary,
    )

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
    return results


def main():
    parser = argparse.ArgumentParser(description="Research Paper Discovery Pipeline")
    parser.add_argument("topic", type=str, help="Research topic")
    parser.add_argument("--context", "-c", type=str, default="", help="Additional context")
    parser.add_argument("--top-n", "-n", type=int, default=10, help="Top N papers")
    parser.add_argument("--no-llm-scoring", action="store_true", help="Disable LLM relevance scoring")
    parser.add_argument("--no-summary", action="store_true", help="Skip summarization")
    parser.add_argument("--log-level", type=str, default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    parser.add_argument("--output", "-o", type=str, default=None)
    args = parser.parse_args()

    setup_logging(args.log_level)
    asyncio.run(_run(args))


if __name__ == "__main__":
    main()