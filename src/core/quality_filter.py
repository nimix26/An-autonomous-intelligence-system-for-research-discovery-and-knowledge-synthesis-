"""
core/quality_filter.py — Stage 3: Relative Quality Filter

NO hardcoded citation minimums. Thresholds derived from the retrieved
pool's own distribution. Works across any academic field.

Fix 2: Maturing papers (1-2 years old) must have at least 1 citation.
Truly new papers (current year) are exempt. This prevents zero-citation
preprints from flooding the pool.
"""

import logging
import statistics
from datetime import datetime
from typing import List

from core.config import Config
from core.query_profiler import QueryProfile

logger = logging.getLogger(__name__)


class QualityFilter:
    def apply(self, papers: List[dict], profile: QueryProfile) -> List[dict]:
        if not papers:
            return []

        current_year = datetime.now().year
        recent_cutoff = Config.STAGE3_RECENT_YEAR_CUTOFF
        min_required = Config.STAGE3_MIN_RESULTS
        max_relax = Config.STAGE3_MAX_RELAX_ATTEMPTS

        # Established papers: old enough to have accumulated citations
        old_enough = [
            p for p in papers
            if (p.get("year", 0) or 0) > 0
            and current_year - (p.get("year", 0) or 0) >= recent_cutoff
        ]

        # Recent papers: within the recent_cutoff window
        recent = [p for p in papers if p not in old_enough]

        # ── Fix 2: split recent into truly new vs maturing ──
        # Truly new = published this year (exempt from citation floor)
        # Maturing = 1-2 years old (must have ≥1 citation)
        truly_new = [
            p for p in recent
            if (p.get("year", 0) or 0) >= current_year
        ]
        maturing = [
            p for p in recent
            if (p.get("year", 0) or 0) < current_year
        ]

        maturing_filtered = [
            p for p in maturing
            if (p.get("citation_count", 0) or 0) >= 1
        ]

        logger.info(
            f"   [Stage3] Recent breakdown: "
            f"truly_new={len(truly_new)} (exempt), "
            f"maturing={len(maturing)} → {len(maturing_filtered)} with ≥1 cite"
        )

        # ── Citation percentile filter on established papers ──
        cite_values = [int(p.get("citation_count", 0) or 0) for p in old_enough]
        cite_values = [c for c in cite_values if c >= 0]

        if not cite_values:
            logger.info(f"   [Stage3] No old-enough papers to calibrate — passing all {len(papers)}")
            return papers

        cite_values_sorted = sorted(cite_values)
        pct = max(0, min(99, profile.quality_percentile))
        cutoff_idx = int(len(cite_values_sorted) * (100 - pct) / 100)
        cutoff_idx = max(0, min(len(cite_values_sorted) - 1, cutoff_idx))
        cite_threshold = cite_values_sorted[cutoff_idx]

        try:
            median_val = statistics.median(cite_values)
        except statistics.StatisticsError:
            median_val = 0

        logger.info(f"   [Stage3] Pool: n={len(cite_values)}, median={median_val:.0f}, "
                    f"keep top {pct}% → threshold={cite_threshold}")

        passed = [p for p in old_enough
                  if int(p.get("citation_count", 0) or 0) >= cite_threshold]
        # Combine: established + truly new + maturing-with-traction
        passed = passed + truly_new + maturing_filtered

        # Progressive relaxation if too few results
        relax = 1
        while len(passed) < min_required and relax <= max_relax and cite_threshold > 0:
            cite_threshold = max(0, cite_threshold // 2)
            passed = [p for p in old_enough
                      if int(p.get("citation_count", 0) or 0) >= cite_threshold]
            passed = passed + truly_new + maturing_filtered
            relax += 1
            logger.info(f"   [Stage3] Relaxed (attempt {relax}) → threshold={cite_threshold}, "
                        f"passed={len(passed)}")

        if len(passed) < min_required:
            # Final fallback: pass everything (including unfiltered maturing)
            passed = list(papers)
            logger.info(f"   [Stage3] Final fallback — passing all {len(passed)}")

        established_count = max(0, len(passed) - len(truly_new) - len(maturing_filtered))
        logger.info(
            f"   [Stage3] Input {len(papers)} → passed {len(passed)} "
            f"({established_count} established + {len(truly_new)} truly new + "
            f"{len(maturing_filtered)} maturing)"
        )
        return passed