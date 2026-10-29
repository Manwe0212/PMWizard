"""Provider abstraction for structured AI generation."""

from __future__ import annotations

from typing import Protocol, TypeVar

from pydantic import BaseModel


StructuredOutput = TypeVar("StructuredOutput", bound=BaseModel)


class AIProviderError(RuntimeError):
    """Raised when a configured AI provider cannot return valid output."""


class StructuredGenerationProvider(Protocol):
    @property
    def provider_name(self) -> str: ...

    @property
    def model_name(self) -> str: ...

    def generate(
        self,
        *,
        instructions: str,
        input_text: str,
        output_type: type[StructuredOutput],
    ) -> StructuredOutput: ...


class OpenAIResponsesProvider:
    """OpenAI Responses API adapter using Pydantic Structured Outputs."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
    ) -> None:
        if not api_key.strip():
            raise ValueError("OpenAI API key must not be empty")
        if not model.strip():
            raise ValueError("OpenAI model must not be empty")

        from openai import OpenAI

        self._client = OpenAI(api_key=api_key)
        self._model = model.strip()

    @property
    def provider_name(self) -> str:
        return "openai"

    @property
    def model_name(self) -> str:
        return self._model

    def generate(
        self,
        *,
        instructions: str,
        input_text: str,
        output_type: type[StructuredOutput],
    ) -> StructuredOutput:
        try:
            response = self._client.responses.parse(
                model=self._model,
                instructions=instructions,
                input=input_text,
                text_format=output_type,
                store=False,
            )
        except Exception as exc:
            raise AIProviderError(
                f"Structured generation failed: {type(exc).__name__}"
            ) from exc

        parsed = response.output_parsed
        if parsed is None:
            raise AIProviderError(
                "AI provider returned no parsed structured output"
            )
        return parsed
