"""
Empirical Bayes CRM Historical Prior Bootstrapper
=================================================
Paranoia Layer 0, 1 & 2 Defense for Bayesian ICP Cold-Start Calibration.

Why this is necessary:
- Default static priors (e.g. Beta(3, 2)) are blind to a company's real historical performance.
- When an enterprise connects HubSpot, Salesforce, or imports a CSV of historical deals,
  this engine bootstraps empirical Bayes Beta priors directly from real win/loss outcomes,
  giving high Day-1 calibration accuracy without waiting for 100 new campaign sends.
"""

import math
import logging
from typing import Dict, List, Any, Tuple, Optional

logger = logging.getLogger(__name__)

MIN_ALPHA = 2
MIN_BETA = 2
DEFAULT_PRIOR_STRENGTH = 10.0  # Effective pseudo-observation sample size


def compute_empirical_beta_prior(
    wins: int,
    losses: int,
    prior_strength: float = DEFAULT_PRIOR_STRENGTH,
    baseline_win_rate: float = 0.50
) -> Tuple[int, int, float]:
    """
    Computes an empirical Bayes Beta(alpha, beta) prior from historical wins and losses.
    Returns: (alpha, beta, estimated_win_rate)
    """
    total = max(0, int(wins)) + max(0, int(losses))
    if total == 0:
        # Fall back to baseline
        alpha = max(MIN_ALPHA, int(round(prior_strength * baseline_win_rate)))
        beta = max(MIN_BETA, int(round(prior_strength * (1.0 - baseline_win_rate))))
        return alpha, beta, baseline_win_rate

    # Smoothed empirical win rate
    empirical_rate = (wins + 1.0) / (total + 2.0)
    alpha = max(MIN_ALPHA, int(round(prior_strength * empirical_rate)))
    beta = max(MIN_BETA, int(round(prior_strength * (1.0 - empirical_rate))))
    return alpha, beta, round(empirical_rate, 4)


def bootstrap_priors_from_crm_deals(
    deals: List[Dict[str, Any]],
    prior_strength: float = DEFAULT_PRIOR_STRENGTH
) -> Dict[str, Dict[str, Any]]:
    """
    Analyzes historical CRM opportunities or lead outcomes and extracts custom
    Bayesian signal priors.

    Expected deal schema:
    {
        "outcome": "won" | "lost" | "closed_won" | "closed_lost",
        "signals": {
            "is_decision_maker": bool,
            "is_target_industry": bool,
            "is_target_size": bool,
            "has_funding": bool,
            ...
        }
    }
    """
    if not deals:
        return {}

    signal_counts: Dict[str, Dict[str, int]] = {}

    for deal in deals:
        if not isinstance(deal, dict):
            continue

        raw_outcome = str(deal.get("outcome") or deal.get("stage") or "").lower().strip()
        is_win = raw_outcome in ("won", "closed_won", "meeting_booked", "positive_reply", "closed-won")
        is_loss = raw_outcome in ("lost", "closed_lost", "ghosted", "rejected", "closed-lost")

        if not is_win and not is_loss:
            continue

        signals = deal.get("signals") or {}
        if not isinstance(signals, dict):
            continue

        for sig_name, is_present in signals.items():
            if not is_present:
                continue
            clean_name = str(sig_name).strip().lower()
            if clean_name not in signal_counts:
                signal_counts[clean_name] = {"wins": 0, "losses": 0}

            if is_win:
                signal_counts[clean_name]["wins"] += 1
            else:
                signal_counts[clean_name]["losses"] += 1

    calibrated_priors = {}
    for sig_name, counts in signal_counts.items():
        alpha, beta, win_rate = compute_empirical_beta_prior(
            counts["wins"],
            counts["losses"],
            prior_strength=prior_strength
        )
        calibrated_priors[sig_name] = {
            "prior_alpha": alpha,
            "prior_beta": beta,
            "historical_wins": counts["wins"],
            "historical_losses": counts["losses"],
            "empirical_win_rate": win_rate,
            "weight": round(alpha / (alpha + beta), 4)
        }

    return calibrated_priors
