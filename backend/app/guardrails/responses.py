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
``_SAFE_FALLBACK_INTRO``. That is a deliberate, narrow exception to "no
hardcoded user-facing string" — losing already-known emergency contacts to
an LLM hiccup is worse than one line of plain English. For an
``out_of_scope`` match, where there are no resources to protect, a failed
generation call still raises, and ``stream_chat_turn``'s existing exception
handling reports the same generic error it already reports for any other
LLM failure.
"""

import asyncio
import logging
from typing import Final

from starlette.concurrency import run_in_threadpool

from app.guardrails.classifier import GuardrailCategory, GuardrailMatch
from app.guardrails.resources import CrisisResource, load_crisis_resources
from app.prompts import load_prompt
from app.services.llm_service import LLMService

logger = logging.getLogger(__name__)

# A stalled Ollama call must not leave a chat SSE stream open with no terminal event.
# Local CPU inference in manual testing took up to ~45s for a single call, so this is
# generous rather than tight; tune per deployment/model if it proves wrong either way.
_INTRO_TIMEOUT_SECONDS: Final[float] = 60.0

# Used only when a crisis/legal-sensitive match has resources to show but the localized
# intro call failed (error or timeout) — see the module docstring.
_SAFE_FALLBACK_INTRO: Final[str] = "Please contact one of these services:"

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


async def build_guardrail_response(match: GuardrailMatch, message: str, llm_service: LLMService) -> str:
    """Compose the user-facing text for a guardrail interception, in the user's own language.

    Args:
        match: The classifier's decision for this message.
        message: The user's original message, used only to detect language and tone.
        llm_service: The LLM service used to generate the localized intro sentence.

    Returns:
        Response text to show instead of a RAG answer.

    Raises:
        RuntimeError: If localized intro generation fails and there are no resources to
            fall back with (i.e. an ``out_of_scope`` match, or a crisis/legal-sensitive
            match whose resource categories have no entries).
    """
    resources: tuple[CrisisResource, ...] = ()
    if match.category is not GuardrailCategory.OUT_OF_SCOPE:
        resources = load_crisis_resources().by_categories(match.resource_categories)

    try:
        intro = await _localized_intro(match.category, message, llm_service)
    except RuntimeError:
        if not resources:
            raise
        logger.warning(
            "Guardrail intro generation failed for a %s match with known resources; "
            "using the safe fallback intro instead of losing the resource list.",
            match.category,
        )
        intro = _SAFE_FALLBACK_INTRO

    if not resources:
        return intro

    lines = [intro, ""]
    lines.extend(_format_resource(resource) for resource in resources)
    return "\n".join(lines)


async def _localized_intro(category: GuardrailCategory, message: str, llm_service: LLMService) -> str:
    """Generate the category's explanatory sentence in the user's own language.

    Args:
        category: The matched guardrail category.
        message: The user's original message, used only to detect language and tone.
        llm_service: The LLM service used for the generation call.

    Returns:
        A short localized paragraph.

    Raises:
        RuntimeError: If the LLM call fails, times out, or returns something unusable.
    """
    prompt = load_prompt(
        "guardrail_response_intro",
        intent_description=_INTENT_DESCRIPTIONS[category],
        message=message,
    )
    try:
        async with asyncio.timeout(_INTRO_TIMEOUT_SECONDS):
            raw_response = await run_in_threadpool(llm_service.generate_response, prompt=prompt)
    except TimeoutError:
        raw_response = None

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
