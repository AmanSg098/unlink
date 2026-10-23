"""LLM drafting. Produces text for humans to review; never reads or writes selection, ratings, amounts or sends.

Nothing in scoring, fairness, workflow, FNF or sending code imports this module (enforced by a test).
Prompts carry employee codes and role-level facts only: no names, salaries, demographics, leave or health data.
Free text (grievance descriptions, questions) is redacted before it is sent.
"""

import json
import logging
import re

import anthropic

log = logging.getLogger(__name__)

MODEL = "claude-opus-5-5"

SYSTEM = """You draft text for HR professionals who plan and carry out workforce reductions in a tool called \
Unlink: plan summaries, ranking explanations, notice wording, grievance summaries and replies. A human reviews \
and edits everything you write, and nothing you write is sent or acted on without their approval.

Rules:
- Use only the facts in the provided data. Do not invent numbers, people, reasons or context.
- You are not a decision-maker. Do not recommend adding or removing specific people, changing weights, \
or approving or rejecting the plan. If the data shows a fairness flag or a gap between target and \
proposed headcount, describe it neutrally as something for the reviewers to examine.
- Refer to employees only by employee code. Never mention protected characteristics, health or leave.
- The ranking comes from deterministic weighted scoring; describe it accurately as such.
- Write in plain, neutral, respectful language. Markdown headings and bullet points are fine. \
Do not give legal advice."""


class AiError(RuntimeError):
    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code


def generate(task: str, data: dict) -> tuple[str, str]:
    """Return (draft_text, model_id). Raises AiError with an HTTP-ish status code."""
    client = anthropic.Anthropic()
    try:
        resp = client.beta.messages.create(
            model=MODEL,
            max_tokens=16000,
            # Server-side fallback re-runs a declined request on another model inside the same call.
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            output_config={"effort": "medium"},
            system=SYSTEM,
            messages=[{
                "role": "user",
                "content": f"{task}\n\n<data>\n{json.dumps(data, indent=2, default=str)}\n</data>",
            }],
        )
    except TypeError as exc:  # raised before any request when no credentials are configured
        raise AiError(503, "AI drafting is not configured: set ANTHROPIC_API_KEY for the API server") from exc
    except anthropic.AuthenticationError as exc:
        raise AiError(503, "AI drafting is not configured: the Anthropic API key was rejected") from exc
    except anthropic.RateLimitError as exc:
        raise AiError(429, "AI service is rate limited; try again shortly") from exc
    except anthropic.APIStatusError as exc:
        log.warning("anthropic api error status=%s", exc.status_code)
        raise AiError(502, f"AI service error ({exc.status_code})") from exc
    except anthropic.APIConnectionError as exc:
        raise AiError(502, "Could not reach the AI service") from exc

    if resp.stop_reason == "refusal":
        raise AiError(422, "The AI declined to draft this text")
    text = "".join(b.text for b in resp.content if b.type == "text").strip()
    if resp.stop_reason == "max_tokens":
        text += "\n\n_[Draft truncated at the length limit.]_"
    log.info("ai draft generated model=%s output_tokens=%s", resp.model, resp.usage.output_tokens)
    return text, resp.model


_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(\.[\w-]+)+")
_PHONE = re.compile(r"(?<!\d)(\+?\d[\d\s-]{8,}\d)(?!\d)")


def redact(text: str, names: list[str], code: str) -> str:
    """Replace the person's name parts with their code; mask emails and phone numbers."""
    out = _EMAIL.sub("[email]", text)
    out = _PHONE.sub("[phone]", out)
    for n in sorted({p for name in names for p in [name, *name.split()] if len(p) > 2}, key=len, reverse=True):
        out = re.sub(r"\b" + re.escape(n) + r"\b", code, out, flags=re.IGNORECASE)
    return out
