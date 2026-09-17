from fastapi import APIRouter, HTTPException

from app.reasoning.summarizer import (
    SummarizationError,
    summarizer,
)
from app.reasoning.topics import (
    TopicExtractionError,
    topic_extractor,
)
from app.schemas.reasoning import (
    ReasoningRequest,
    ReasoningResponse,
)


router = APIRouter(
    prefix="/api/media",
    tags=["AI Reasoning"],
)


@router.post(
    "/reason",
    response_model=ReasoningResponse,
)
def reason_about_media(
    request: ReasoningRequest,
) -> ReasoningResponse:
    """
    Perform AI reasoning on an already processed
    deterministic media result.

    This endpoint does NOT process the original media.
    It receives the NormalizedMediaDocument produced
    by the deterministic pipeline.
    """

    document = request.normalized

    # Convert the normalized document into a plain
    # structure that can safely be provided to the
    # reasoning components.
    evidence = _extract_evidence(document)

    if not evidence:
        raise HTTPException(
            status_code=422,
            detail=(
                "The normalized document contains no "
                "deterministic evidence for reasoning."
            ),
        )

    try:
        topics_result = topic_extractor.extract(
            evidence
        )

        summary_result = summarizer.summarize(
            evidence
        )

    except TopicExtractionError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Topic extraction failed: {exc}",
        ) from exc

    except SummarizationError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Summarization failed: {exc}",
        ) from exc

    return ReasoningResponse(
        document_id=document.document_id,
        topics=[
            {
                "name": topic.name,
                "description": topic.description,
            }
            for topic in topics_result.topics
        ],
        summary=summary_result.summary,
    )


def _extract_evidence(
    document,
) -> list[dict]:
    """
    Extract deterministic evidence from the normalized
    document without sending the entire media object
    blindly to the LLM.

    The normalized schema may contain evidence in
    different content/artifact structures depending
    on the media processor, so this helper keeps the
    reasoning endpoint independent from those details.
    """

    evidence: list[dict] = []

    # Explicit evidence/provenance attached to the
    # normalized document.
    for item in document.provenance:
        if hasattr(item, "model_dump"):
            evidence.append(item.model_dump())
        elif isinstance(item, dict):
            evidence.append(item)

    # Include normalized textual content when present.
    content = document.content

    if content is not None and hasattr(content, "model_dump"):
        content_data = content.model_dump()

        if content_data:
            evidence.append(
                {
                    "type": "normalized_content",
                    "content": content_data,
                }
            )

    elif isinstance(content, dict) and content:
        evidence.append(
            {
                "type": "normalized_content",
                "content": content,
            }
        )

    return evidence

