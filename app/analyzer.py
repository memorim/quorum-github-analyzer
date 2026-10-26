from __future__ import annotations

from datetime import UTC, datetime
from typing import Any


def _parse_github_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return result.replace(tzinfo=UTC) if result.tzinfo is None else result
    except (ValueError, AttributeError):
        return None


def _risk(severity: str, title: str, detail: str) -> dict[str, str]:
    return {"severity": severity, "title": title, "detail": detail}


def _action(priority: str, title: str, why: str) -> dict[str, str]:
    return {"priority": priority, "title": title, "why": why}


def triage_issues(
    issues: list[dict[str, Any]], now: datetime | None = None
) -> list[dict[str, Any]]:
    current = now or datetime.now(UTC)
    triaged: list[dict[str, Any]] = []

    for issue in issues:
        labels = {
            str(label.get("name", "")).lower()
            for label in issue.get("labels", [])
            if isinstance(label, dict)
        }
        created_at = _parse_github_date(issue.get("created_at")) or current
        age_days = max((current - created_at).days, 0)
        comments = int(issue.get("comments", 0))
        score = min(age_days // 7, 8) + min(comments, 10)

        if any("security" in label for label in labels):
            score += 30
        if any(label in {"bug", "type:bug"} for label in labels):
            score += 12
        if any("high" in label or "urgent" in label for label in labels):
            score += 15

        priority = (
            "critical"
            if score >= 35
            else "high"
            if score >= 20
            else "medium"
            if score >= 10
            else "low"
        )
        triaged.append(
            {
                "number": issue.get("number"),
                "title": issue.get("title", "Untitled issue"),
                "url": issue.get("html_url"),
                "priority": priority,
                "priority_score": score,
                "age_days": age_days,
                "comments": comments,
                "labels": sorted(labels),
            }
        )

    return sorted(triaged, key=lambda item: item["priority_score"], reverse=True)


def analyze_repository_bundle(
    bundle: dict[str, Any],
    now: datetime | None = None,
) -> dict[str, Any]:
    current = now or datetime.now(UTC)
    repository = bundle["repository"]
    languages = bundle.get("languages", {})
    issues = bundle.get("issues", [])
    pulls = bundle.get("pulls", [])
    workflow_runs = bundle.get("workflow_runs", [])
    collection = bundle.get("collection", {})

    score = 100
    risks: list[dict[str, str]] = []
    actions: list[dict[str, str]] = []

    pushed_at = _parse_github_date(repository.get("pushed_at"))
    days_since_push = max(0, (current - pushed_at).days) if pushed_at else None
    if days_since_push is not None and days_since_push > 180:
        score -= 25
        risks.append(
            _risk("high", "Repository is inactive", f"No push for {days_since_push} days.")
        )
        actions.append(
            _action("high", "Plan a maintenance release", "Restore a visible delivery cadence.")
        )
    elif days_since_push is not None and days_since_push > 60:
        score -= 12
        risks.append(
            _risk("medium", "Delivery cadence slowed", f"Last push was {days_since_push} days ago.")
        )

    if repository.get("archived"):
        score -= 30
        risks.append(
            _risk("high", "Repository is archived", "New changes and issue handling are disabled.")
        )

    if not repository.get("description"):
        score -= 8
        risks.append(
            _risk(
                "low",
                "Missing repository description",
                "The project purpose is unclear in search results.",
            )
        )
        actions.append(
            _action(
                "medium", "Add a concise description", "Improve discoverability and onboarding."
            )
        )

    if not repository.get("license"):
        score -= 10
        risks.append(
            _risk("medium", "No license detected", "Reuse and contribution terms are ambiguous.")
        )
        actions.append(
            _action(
                "high", "Choose and add a license", "Clarify legal usage and contribution terms."
            )
        )

    topics = repository.get("topics") or []
    if not topics:
        score -= 5
        actions.append(
            _action("low", "Add repository topics", "Make the project easier to discover.")
        )

    issue_count = len(issues)
    if issue_count > 60:
        score -= 20
        risks.append(
            _risk("high", "Large issue backlog", f"{issue_count} open issues need triage.")
        )
    elif issue_count > 20:
        score -= 10
        risks.append(
            _risk("medium", "Issue backlog is growing", f"{issue_count} open issues need review.")
        )

    open_pull_count = len(pulls)
    if open_pull_count > 10:
        score -= 8
        risks.append(
            _risk(
                "medium",
                "Pull request queue is congested",
                f"{open_pull_count} pull requests are open.",
            )
        )

    concluded_runs = [run for run in workflow_runs if run.get("conclusion")]
    successful_runs = sum(run.get("conclusion") == "success" for run in concluded_runs)
    ci_success_rate = successful_runs / len(concluded_runs) if concluded_runs else None
    if not workflow_runs and collection.get("workflow_runs", {}).get("available", True):
        score -= 12
        risks.append(
            _risk(
                "medium", "No recent CI runs found", "Automated validation is missing or inactive."
            )
        )
        actions.append(
            _action("high", "Add a CI quality gate", "Run tests and linting on every pull request.")
        )
    elif ci_success_rate is not None and ci_success_rate < 0.6:
        score -= 15
        risks.append(
            _risk(
                "high",
                "CI reliability is low",
                f"Only {ci_success_rate:.0%} of recent runs passed.",
            )
        )
        actions.append(
            _action(
                "high",
                "Stabilize failing workflows",
                "Reliable feedback keeps pull requests moving.",
            )
        )

    incomplete = [
        name for name, state in collection.items() if not state["available"] or state["truncated"]
    ]
    if incomplete or pushed_at is None:
        risks.append(
            _risk(
                "low",
                "Incomplete metadata snapshot",
                "Unavailable or bounded samples: " + ", ".join(incomplete or ["last push date"]),
            )
        )
    if not risks:
        risks.append(
            _risk("low", "No immediate risks detected", "The repository signals look healthy.")
        )
    if not actions:
        actions.append(
            _action(
                "low",
                "Keep the current engineering cadence",
                "No urgent corrective action is required.",
            )
        )

    language_total = sum(int(value) for value in languages.values()) or 1
    language_mix = [
        {"name": name, "share": round((int(value) / language_total) * 100, 1)}
        for name, value in sorted(languages.items(), key=lambda item: item[1], reverse=True)[:5]
    ]

    score = max(0, min(score, 100))
    if score >= 85:
        verdict = "Strong metadata maintenance signals"
    elif score >= 70:
        verdict = "Healthy with a few visible gaps"
    elif score >= 50:
        verdict = "Needs focused maintenance"
    else:
        verdict = "Metadata indicates maintenance gaps"
    if incomplete:
        verdict += " (partial snapshot)"

    triaged_issues = triage_issues(issues, current)
    metrics = {
        "stars": int(repository.get("stargazers_count", 0)),
        "forks": int(repository.get("forks_count", 0)),
        "open_issues": issue_count,
        "open_pulls": open_pull_count,
        "days_since_push": days_since_push,
        "ci_success_rate": round(ci_success_rate * 100, 1) if ci_success_rate is not None else None,
        "default_branch": repository.get("default_branch", "main"),
        "language_mix": language_mix,
        "analysis_scope": "github_metadata_only",
        "collection": collection,
        "analyzed_at": current.isoformat(),
    }

    return {
        "repository": repository.get("full_name", "unknown/unknown"),
        "repository_url": repository.get("html_url"),
        "score": score,
        "verdict": verdict,
        "summary": (
            f"{repository.get('full_name', 'Repository')} scored {score}/100. "
            f"Quorum found {len(risks)} risk signal(s) and {len(actions)} recommended action(s)."
        ),
        "metrics": metrics,
        "risks": risks,
        "actions": actions,
        "triaged_issues": triaged_issues[:8],
    }
