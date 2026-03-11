"""Quality metrics calculator for SDD generation runs."""

from ard.state import ARDState


def calculate_quality_metrics(state: ARDState) -> dict:
    """Calculate quality metrics for a completed SDD generation run.

    Returns:
        dict with keys:
            - verified_at_round: int | None - Which round verification happened (None if timed out)
            - total_rounds: int - Total review rounds
            - critical_issues: int - Total critical issues found across all rounds
            - minor_issues: int - Total minor issues found across all rounds
            - total_issues_addressed: int - Issues from all rounds except final
            - user_clarifications: int - Number of HITL decisions
            - quality_score: int - 0-100 score based on efficiency and quality
            - quality_label: str - Human-readable quality assessment
    """
    challenge_history = state.get("challenge_history", [])
    user_clarifications = state.get("user_clarifications", [])
    status = state.get("status", "in_progress")
    iteration = state.get("iteration", 0)

    total_rounds = len(challenge_history)

    # Count issues by severity across all rounds
    total_critical = 0
    total_minor = 0
    for round_data in challenge_history:
        challenges = round_data.get("challenges", [])
        total_critical += sum(1 for c in challenges if c.get("severity") == "critical")
        total_minor += sum(1 for c in challenges if c.get("severity") == "minor")

    # Issues addressed = all issues except those in final round
    total_issues_addressed = 0
    if total_rounds > 1:
        for round_data in challenge_history[:-1]:
            challenges = round_data.get("challenges", [])
            total_issues_addressed += len(challenges)

    # Determine verification round
    verified_at_round = None
    if status == "verified":
        # Find the round where verification happened (status became "verified")
        for i, round_data in enumerate(challenge_history, 1):
            if round_data.get("status") == "verified":
                verified_at_round = i
                break

    hitl_count = len(user_clarifications)

    # Calculate quality score (0-100)
    quality_score = 100

    # Deduct for multiple rounds (each round beyond first costs 5 points)
    if verified_at_round:
        quality_score -= (verified_at_round - 1) * 5
    elif status == "max_iterations_reached":
        quality_score -= total_rounds * 5  # Full penalty for timeout

    # Deduct for critical issues (10 points each from first round)
    if challenge_history:
        first_round_critical = sum(
            1 for c in challenge_history[0].get("challenges", [])
            if c.get("severity") == "critical"
        )
        quality_score -= first_round_critical * 10

    # Deduct for user interventions (5 points each)
    quality_score -= hitl_count * 5

    # Additional penalty for timeout
    if status == "max_iterations_reached":
        quality_score -= 20

    # Floor at 0
    quality_score = max(0, quality_score)

    # Quality label
    if quality_score >= 90:
        quality_label = "Excellent"
    elif quality_score >= 75:
        quality_label = "Good"
    elif quality_score >= 60:
        quality_label = "Fair"
    elif quality_score >= 40:
        quality_label = "Acceptable"
    else:
        quality_label = "Needs Improvement"

    return {
        "verified_at_round": verified_at_round,
        "total_rounds": total_rounds,
        "critical_issues": total_critical,
        "minor_issues": total_minor,
        "total_issues_addressed": total_issues_addressed,
        "user_clarifications": hitl_count,
        "quality_score": quality_score,
        "quality_label": quality_label,
    }
