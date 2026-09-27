"""Resolve A2A Agent Cards: Nacos first, then well-known HTTP fallback."""

from __future__ import annotations

import asyncio
import logging
import os
from a2a.client.card_resolver import A2ACardResolver
from a2a.types import AgentCard
from httpx import AsyncClient

from logging_config import log_event

logger = logging.getLogger(__name__)

_FALLBACK_URLS = {
    "portfolio": os.environ.get("PORTFOLIO_A2A_BASE_URL", "http://portfolio:8110"),
    "research": os.environ.get("RESEARCH_A2A_BASE_URL", "http://research:8120"),
}


def _nacos_server_addr() -> str:
    return os.environ.get("NACOS_SERVER_ADDR", "nacos:8848")


class NacosAgentCardResolver:
    """Fetch an Agent Card from the Nacos A2A registry (AgentScope path)."""

    def __init__(
        self,
        remote_agent_name: str,
        *,
        nacos_server_addr: str | None = None,
    ) -> None:
        self.remote_agent_name = remote_agent_name
        self.nacos_server_addr = nacos_server_addr or _nacos_server_addr()

    async def get_agent_card(self) -> AgentCard:
        from v2.nacos import ClientConfigBuilder
        from v2.nacos.ai.model.ai_param import GetAgentCardParam
        from v2.nacos.ai.nacos_ai_service import NacosAIService

        builder = ClientConfigBuilder().server_address(self.nacos_server_addr)
        username = os.environ.get("NACOS_USERNAME")
        password = os.environ.get("NACOS_PASSWORD")
        if username and password:
            builder.username(username).password(password)
        service = await NacosAIService.create_ai_service(builder.build())
        try:
            detail = await service.get_agent_card(
                GetAgentCardParam(agent_name=self.remote_agent_name)
            )
        finally:
            try:
                await service.shutdown()
            except Exception:
                logger.debug("Nacos AI service shutdown failed", exc_info=True)
        if isinstance(detail, AgentCard):
            return AgentCard.model_validate(detail.model_dump())
        if isinstance(detail, dict):
            return AgentCard.model_validate(detail)
        raise TypeError(f"Unexpected agent card type: {type(detail)!r}")


async def _card_from_well_known(base_url: str) -> AgentCard:
    async with AsyncClient(timeout=10.0) as client:
        resolver = A2ACardResolver(httpx_client=client, base_url=base_url)
        return await resolver.get_agent_card()


async def discover_agent_card(
    agent_name: str,
    *,
    attempts: int = 30,
    delay_seconds: float = 2.0,
) -> AgentCard:
    """Retry Nacos discovery, then the specialist's well-known Agent Card URL."""
    last_error: Exception | None = None
    resolver = NacosAgentCardResolver(agent_name)
    fallback = _FALLBACK_URLS.get(agent_name)
    for attempt in range(1, attempts + 1):
        try:
            card = await resolver.get_agent_card()
            log_event(
                logger,
                logging.INFO,
                "a2a.discover.completed",
                f"Discovered {agent_name} via Nacos",
                agent_name=agent_name,
                source="nacos",
                attempt=attempt,
            )
            return card
        except Exception as exc:
            last_error = exc
            log_event(
                logger,
                logging.INFO,
                "a2a.discover.retry",
                f"Nacos discovery for {agent_name} not ready ({type(exc).__name__})",
                agent_name=agent_name,
                source="nacos",
                attempt=attempt,
                error_type=type(exc).__name__,
            )
        if fallback:
            try:
                card = await _card_from_well_known(fallback)
                log_event(
                    logger,
                    logging.INFO,
                    "a2a.discover.completed",
                    f"Discovered {agent_name} via well-known card",
                    agent_name=agent_name,
                    source="well_known",
                    attempt=attempt,
                )
                return card
            except Exception as exc:
                last_error = exc
        await asyncio.sleep(delay_seconds)
    raise RuntimeError(
        f"Could not discover A2A agent {agent_name!r} after {attempts} attempts"
    ) from last_error
