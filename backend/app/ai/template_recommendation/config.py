from __future__ import annotations

from pathlib import Path

from app.ai.system_config import (
    BACKEND_ROOT,
    PROJECT_ROOT,
    system_ai_config,
    system_ai_env,
)


class TemplateRecommendationSettings:
    @property
    def section(self):
        return system_ai_config.template_recommendation

    @property
    def resolved_templates_dir(self) -> Path:
        path = Path(self.section.templates_dir)
        if path.is_absolute():
            return path

        backend_relative = (BACKEND_ROOT / path).resolve()
        if backend_relative.exists():
            return backend_relative

        return (PROJECT_ROOT / path).resolve()

    @property
    def parsed_backend_node_gpu_map(self) -> dict[str, int]:
        parsed: dict[str, int] = {}
        for key, value in self.section.backend_node_gpu_map.items():
            try:
                parsed[str(key)] = max(int(value), 0)
            except (TypeError, ValueError):
                continue
        return parsed

    @property
    def vllm_base_url(self) -> str:
        return system_ai_env.vllm_base_url

    @property
    def vllm_api_key(self) -> str:
        return system_ai_env.vllm_api_key

    @property
    def resolved_vllm_model_name(self) -> str:
        return system_ai_env.vllm_model_name.strip()

    @property
    def vllm_enable_thinking(self) -> bool:
        return bool(self.section.vllm.enable_thinking)

    @property
    def vllm_timeout(self) -> int:
        return int(self.section.vllm.timeout)

    @property
    def vllm_temperature(self) -> float:
        return float(self.section.vllm.temperature)

    @property
    def vllm_chat_temperature(self) -> float:
        if self.section.vllm.chat_temperature is not None:
            return float(self.section.vllm.chat_temperature)
        return self.vllm_temperature

    @property
    def vllm_top_p(self) -> float:
        return float(self.section.vllm.top_p)

    @property
    def vllm_top_k(self) -> int:
        return int(self.section.vllm.top_k)

    @property
    def vllm_min_p(self) -> float:
        return float(self.section.vllm.min_p)

    @property
    def vllm_max_tokens(self) -> int:
        return int(self.section.vllm.max_tokens)

    @property
    def vllm_chat_max_tokens(self) -> int:
        if self.section.vllm.chat_max_tokens is not None:
            return int(self.section.vllm.chat_max_tokens)
        return self.vllm_max_tokens

    @property
    def vllm_presence_penalty(self) -> float:
        if self.section.vllm.presence_penalty is not None:
            return float(self.section.vllm.presence_penalty)
        return 0.0

    @property
    def vllm_repetition_penalty(self) -> float:
        return float(self.section.vllm.repetition_penalty)


settings = TemplateRecommendationSettings()
