"""Agent plugin — registers agent-enhanced routes on an existing FastAPI app.

This is the ONLY integration point between the agent framework and the main
application. Import and call ``register_agents(app)`` to add agent endpoints.
"""

import logging

from fastapi import FastAPI

logger = logging.getLogger(__name__)


def register_agents(app: FastAPI) -> None:
    """Register agent-enhanced routers on the given FastAPI app.

    Also ensures ``mto_config`` is available on ``app.state`` (the agent
    tools need it, but the original main.py stores it only on the handler).

    Args:
        app: The FastAPI application instance from src.main.
    """
    from src.api.routers import agent_chat

    app.include_router(agent_chat.router)
    logger.info("Agent-enhanced chat registered at /api/agent-chat/")

    # Use middleware to lazily expose mto_config on app.state.
    # The lifespan in main.py stores mto_config on the handler but not
    # on app.state directly. We copy it on first request so the agent
    # tools can find it.
    _mto_config_exposed = False

    @app.middleware("http")
    async def _ensure_mto_config(request, call_next):
        nonlocal _mto_config_exposed
        if not _mto_config_exposed:
            if not hasattr(app.state, "mto_config"):
                handler = getattr(app.state, "mto_handler", None)
                if handler and hasattr(handler, "_mto_config"):
                    app.state.mto_config = handler._mto_config
                    logger.info("Exposed mto_config on app.state from mto_handler")
            _mto_config_exposed = True
        return await call_next(request)
