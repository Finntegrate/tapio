"""User-facing copy for guardrail interceptions (#29)."""

from app.guardrails.classifier import GuardrailCategory, GuardrailMatch
from app.guardrails.resources import CrisisResource, load_crisis_resources

_OUT_OF_SCOPE_MESSAGE = (
    "I'm built to help with settling in Finland — immigration, work, benefits, housing, and daily "
    "life. That question is outside what I can help with here. For general questions, try a "
    "general-purpose search engine or assistant; for Finland-specific topics, ask me about permits, "
    "jobs, benefits, or housing."
)

_CRISIS_INTRO = (
    "This sounds like it might be urgent, and I'm not the right place for that kind of support. "
    "Please reach out to one of these services — they're better placed to help than I am:"
)

_LEGAL_SENSITIVE_INTRO = (
    "This touches on a legal process I'm not qualified to advise on directly. I can share general, "
    "sourced information, but for guidance on your specific situation, please contact:"
)


def build_guardrail_response(match: GuardrailMatch) -> str:
    """Compose the user-facing text for a guardrail interception.

    Args:
        match: The classifier's decision for this message.

    Returns:
        Response text to show instead of a RAG answer.
    """
    if match.category is GuardrailCategory.OUT_OF_SCOPE:
        return _OUT_OF_SCOPE_MESSAGE

    intro = _CRISIS_INTRO if match.category is GuardrailCategory.CRISIS else _LEGAL_SENSITIVE_INTRO
    resources = load_crisis_resources().by_categories(match.resource_categories)
    if not resources:
        return intro

    lines = [intro, ""]
    lines.extend(_format_resource(resource) for resource in resources)
    return "\n".join(lines)


def _format_resource(resource: CrisisResource) -> str:
    """Format one resource as a single Markdown list line.

    Args:
        resource: The resource to format.

    Returns:
        A ``- Name — phone (hours): url`` line, omitting missing fields.
    """
    phone = f" — {resource.phone}" if resource.phone else ""
    hours = f" ({resource.hours})" if resource.hours else ""
    return f"- {resource.name}{phone}{hours}: {resource.url}"
