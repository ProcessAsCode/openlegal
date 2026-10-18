"""Agent layer: planner, working memory, tool broker, guardrail interceptor.

The four components that distinguish an agent from an executor. Imported
lazily by the router so a misconfigured LLM cannot stop the rest of
OpenLegal from booting.
"""
