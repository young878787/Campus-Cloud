from __future__ import annotations

from app.ai.system_config import system_ai_config, system_ai_env


class PVEAdvisorSettings:
    enabled: bool = True

    @property
    def section(self):
        return system_ai_config.pve_advisor

    @property
    def source_cache_ttl_seconds(self) -> int:
        return int(self.section.source_cache_ttl_seconds)

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
    def backend_traffic_window_minutes(self) -> int:
        return int(self.section.backend_traffic_window_minutes)

    @property
    def backend_traffic_sample_limit(self) -> int:
        return int(self.section.backend_traffic_sample_limit)

    @property
    def audit_log_window_minutes(self) -> int:
        return int(self.section.audit_log_window_minutes)

    @property
    def audit_log_sample_limit(self) -> int:
        return int(self.section.audit_log_sample_limit)

    @property
    def guest_pressure_threshold(self) -> float:
        return float(self.section.guest_pressure_threshold)

    @property
    def guest_per_core_limit(self) -> float:
        return float(self.section.guest_per_core_limit)

    @property
    def placement_headroom_ratio(self) -> float:
        return float(self.section.placement_headroom_ratio)

    @property
    def placement_weight_cpu(self) -> float:
        return float(self.section.placement_weight_cpu)

    @property
    def placement_weight_memory(self) -> float:
        return float(self.section.placement_weight_memory)

    @property
    def placement_weight_disk(self) -> float:
        return float(self.section.placement_weight_disk)

    @property
    def placement_weight_guest(self) -> float:
        return float(self.section.placement_weight_guest)

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


settings = PVEAdvisorSettings()
