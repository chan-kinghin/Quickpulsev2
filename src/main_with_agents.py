"""Extended entry point that composes the base app with agent-enhanced routes.

Usage:
    uvicorn src.main_with_agents:app --reload --port 8000

This is the ONLY file that bridges src/main.py and the agent framework.
The base app continues to work standalone via ``uvicorn src.main:app``.
"""

from src.main import app
from src.agents.plugin import register_agents

register_agents(app)
