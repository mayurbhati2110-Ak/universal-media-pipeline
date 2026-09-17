from app.services.llm_service import llm_service


class ReasoningLLM:
    """
    LLM interface for the reasoning layer.

    Uses the shared LLMService so all AI reasoning
    goes through the same FreeLLMAPI configuration.
    """

    def generate(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
        temperature: float = 0.1,
    ) -> str:
        """
        Generate an LLM response for a reasoning task.
        """

        messages: list[dict[str, str]] = []

        if system_prompt:
            messages.append(
                {
                    "role": "system",
                    "content": system_prompt,
                }
            )

        messages.append(
            {
                "role": "user",
                "content": prompt,
            }
        )

        return llm_service.chat(
            messages=messages,
            temperature=temperature,
        )


# Shared reasoning-layer LLM instance
reasoning_llm = ReasoningLLM()

