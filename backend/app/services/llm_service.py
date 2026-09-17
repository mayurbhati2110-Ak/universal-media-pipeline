import os

from dotenv import load_dotenv
from openai import OpenAI


# Explicitly load the .env file
load_dotenv(dotenv_path=".env")


class LLMService:

    def __init__(self):

        self.api_key = os.getenv("LLM_API_KEY")
        self.base_url = os.getenv("LLM_BASE_URL")
        self.model = os.getenv("LLM_MODEL")

        # Validate configuration
        if not self.api_key:
            raise ValueError("LLM_API_KEY is missing from .env")

        if not self.base_url:
            raise ValueError("LLM_BASE_URL is missing from .env")

        if not self.model:
            raise ValueError("LLM_MODEL is missing from .env")

        # Create the OpenAI-compatible client
        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url
        )

    def chat(
        self,
        messages: list,
        temperature: float = 0.1
    ) -> str:
        """
        Send a chat request to FreeLLMAPI.

        FreeLLMAPI handles the underlying model
        selection because LLM_MODEL is set to 'auto'.
        """

        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature
        )

        content = response.choices[0].message.content

        if not content:
            raise ValueError(
                "The LLM returned an empty response."
            )

        return content


# Shared LLM service instance
llm_service = LLMService()
