"""User-facing copy for guardrail interceptions (#29).

The explanatory text has no hardcoded user-facing string: it's generated
per turn by a small, focused LLM call, and asked to reply in the same
language the user wrote in — Tapio can't assume every user writes in
English. Resource contact details (name, phone, hours, URL) are never
sent through that call: they're formatted deterministically from
``crisis_resources.yaml`` and appended verbatim, so a language-generation
step can't rephrase, translate, or hallucinate a phone number or URL.

Resources are loaded before the intro generation call, not after: a
crisis/legal-sensitive match with known resources must still surface them
even if that unrelated LLM call times out or otherwise fails, via
``_SAFE_FALLBACK_INTRO``. Any crisis/legal-sensitive match — including one
with no resources to show (an unmatched category, or one withheld by
``require_approved_crisis_resources``) — falls back to a deterministic,
category-appropriate line (``_SAFE_FALLBACK_INTRO`` or
``_SAFE_FALLBACK_NO_RESOURCES_INTRO``) rather than raising, so a second,
independent failure (the intro call) can never turn a safety-relevant
match into a bare generic error. These are the deliberate, narrow
exceptions to "no hardcoded user-facing string" — a plain English line is
a better outcome than silence for a message already flagged as crisis or
legal-sensitive. Only an ``out_of_scope`` match, which carries no safety
stakes, still raises on a failed generation call, and
``stream_chat_turn``'s existing exception handling reports the same
generic error it already reports for any other LLM failure.

``BackendSettings.require_approved_crisis_resources`` (default off) is a
deployer-controlled, fail-closed serving path: when set, specific contact
details are withheld unless ``crisis_resources.yaml`` has ``status:
approved`` (see docs/specs/crisis-escalation-resources.md and PRD §11).
It defaults off because nothing has shipped to broad release yet and the
governance doc treats sign-off, not a code gate, as the control for the
draft period — but a deployer who wants a hard gate now has one.
"""

import logging
from typing import Final

from starlette.concurrency import run_in_threadpool

from app.config import BackendSettings
from app.guardrails.classifier import GuardrailCategory, GuardrailMatch
from app.guardrails.resources import CrisisResource, load_crisis_resources
from app.prompts import load_prompt
from app.services.llm import LLMProvider

logger = logging.getLogger(__name__)

_APPROVED_STATUS: Final[str] = "approved"

# A stalled Ollama call must not leave a chat SSE stream open with no terminal event.
# Local CPU inference in manual testing took up to ~45s for a single call, so this is
# generous rather than tight; tune per deployment/model if it proves wrong either way.
_INTRO_TIMEOUT_SECONDS: Final[float] = 60.0

# Used only when a crisis/legal-sensitive match has resources to show but the localized
# intro call failed (error or timeout) — see the module docstring.
_SAFE_FALLBACK_INTRO: Final[str] = "Please contact one of these services:"

# Used when a crisis/legal-sensitive match has no resources to show (unmatched category, or
# withheld by require_approved_crisis_resources) and the localized intro call also failed.
_SAFE_FALLBACK_NO_RESOURCES_INTRO: Final[str] = (
    "Please contact your local emergency services or a trusted support line directly."
)

# Fed into the prompt template as an instruction to the model — never shown to
# the user directly, so this is prompt content, not user-facing copy.
_INTENT_DESCRIPTIONS: dict[GuardrailCategory, str] = {
    GuardrailCategory.CRISIS: (
        "Tell them this sounds urgent and Tapio is not the right place for this kind of support, "
        "and that a list of services better placed to help follows below."
    ),
    GuardrailCategory.LEGAL_SENSITIVE: (
        "Tell them this touches on a legal process Tapio is not qualified to advise on directly, "
        "and that contacts for qualified help follow below."
    ),
    GuardrailCategory.OUT_OF_SCOPE: (
        "Tell them briefly and kindly that Tapio only helps with settling in Finland — "
        "immigration, work, benefits, housing, and daily life — and this question is outside "
        "that scope. Suggest they try a general-purpose search engine or assistant instead."
    ),
}

# Used instead of _INTENT_DESCRIPTIONS' crisis/legal_sensitive entries when
# require_approved_crisis_resources withholds the specific contact list, so the
# generated intro doesn't promise a list that won't follow.
_INTENT_DESCRIPTIONS_RESOURCES_WITHHELD: dict[GuardrailCategory, str] = {
    GuardrailCategory.CRISIS: (
        "Tell them this sounds urgent and Tapio is not the right place for this kind of support. "
        "Tapio's specific service contacts for this aren't available right now, so tell them to "
        "contact their country's general emergency number or a local crisis line directly."
    ),
    GuardrailCategory.LEGAL_SENSITIVE: (
        "Tell them this touches on a legal process Tapio is not qualified to advise on directly. "
        "Tapio's specific service contacts for this aren't available right now, so suggest they "
        "search for official Finnish immigration or legal aid services directly."
    ),
}


async def build_guardrail_response(match: GuardrailMatch, message: str, llm_service: LLMProvider) -> str:
    """Compose the user-facing text for a guardrail interception, in the user's own language.

    Args:
        match: The classifier's decision for this message.
        message: The user's original message, used only to detect language and tone.
        llm_service: The LLM service used to generate the localized intro sentence.

    Returns:
        Response text to show instead of a RAG answer.

    Raises:
        RuntimeError: If localized intro generation fails for an ``out_of_scope`` match,
            the only category with no safety stakes and thus no deterministic fallback.
    """
    resources = _resources_for(match)
    is_safety_critical = match.category is not GuardrailCategory.OUT_OF_SCOPE
    intent_descriptions = (
        _INTENT_DESCRIPTIONS
        if resources or match.category is GuardrailCategory.OUT_OF_SCOPE
        else _INTENT_DESCRIPTIONS_RESOURCES_WITHHELD
    )

    try:
        intro = await _localized_intro(match.category, message, llm_service, intent_descriptions)
    except RuntimeError:
        if not is_safety_critical:
            raise
        logger.warning(
            "Guardrail intro generation failed for a safety-critical (%s) match; using a "
            "deterministic fallback intro instead of surfacing a generic error.",
            match.category,
        )
        intro = _SAFE_FALLBACK_INTRO if resources else _SAFE_FALLBACK_NO_RESOURCES_INTRO

    if not resources:
        return intro

    lines = [intro, ""]
    lines.extend(_format_resource(resource) for resource in resources)
    return "\n".join(lines)


def _resources_for(match: GuardrailMatch) -> tuple[CrisisResource, ...]:
    """Resolve the resources a match should surface, honoring the approval gate.

    Args:
        match: The classifier's decision for this message.

    Returns:
        Matching resources, or an empty tuple for an ``out_of_scope`` match, an empty
        ``resource_categories``, or a non-``approved`` list while
        ``require_approved_crisis_resources`` is enabled.
    """
    if match.category is GuardrailCategory.OUT_OF_SCOPE:
        return ()

    resource_list = load_crisis_resources()
    if resource_list.status != _APPROVED_STATUS and BackendSettings().require_approved_crisis_resources:
        logger.warning(
            "Withholding %s resources: crisis_resources.yaml status is %r, not %r, and "
            "require_approved_crisis_resources is enabled.",
            match.category,
            resource_list.status,
            _APPROVED_STATUS,
        )
        return ()

    return resource_list.by_categories(match.resource_categories)


async def _localized_intro(
    category: GuardrailCategory,
    message: str,
    llm_service: LLMProvider,
    intent_descriptions: dict[GuardrailCategory, str],
) -> str:
    """Generate the category's explanatory sentence in the user's own language.

    Args:
        category: The matched guardrail category.
        message: The user's original message, used only to detect language and tone.
        llm_service: The LLM service used for the generation call.
        intent_descriptions: Which intent-description set to draw from — differs depending on
            whether resources will actually follow the generated intro (see ``_resources_for``).

    Returns:
        A short localized paragraph.

    Raises:
        RuntimeError: If the LLM call fails, times out, or returns something unusable.
    """
    prompt = load_prompt(
        "guardrail_response_intro",
        intent_description=intent_descriptions[category],
        message=message,
    )
    # The timeout is enforced by the configured LLMProvider's own client, not by wrapping
    # this (threadpool-dispatched, synchronous) call in asyncio.timeout(): AnyIO's
    # to_thread.run_sync ignores cancellation by default and waits for the worker thread
    # to finish regardless, so an outer asyncio-level timeout would not actually bound a
    # stalled call here. See LLMProvider.generate_response's `timeout` parameter docstring.
    raw_response = await run_in_threadpool(llm_service.generate_response, prompt=prompt, timeout=_INTRO_TIMEOUT_SECONDS)

    if not isinstance(raw_response, str) or not raw_response.strip() or raw_response.startswith("Error:"):
        msg = f"Guardrail response intro generation failed for category {category.value!r}: {raw_response!r}"
        raise RuntimeError(msg)

    return raw_response.strip()


def _format_resource(resource: CrisisResource) -> str:
    """Format one resource as a single Markdown list line.

    Args:
        resource: The resource to format.

    Returns:
        A ``- Name — phone (hours): url`` line, omitting missing fields. Never
        passed through the localized-intro LLM call: names, phone numbers, and
        URLs are proper nouns and contact data, not text to translate.
    """
    phone = f" — {resource.phone}" if resource.phone else ""
    hours = f" ({resource.hours})" if resource.hours else ""
    return f"- {resource.name}{phone}{hours}: {resource.url}"
