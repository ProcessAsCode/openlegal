"""Pydantic v2 schemas for the API surface.

Convention: one module per resource. Within each module:
  - `*Create` for POST bodies (what the client sends to create)
  - `*Update` for PATCH bodies (partial updates)
  - `*Response` for what the API returns

The schemas mirror the SQLAlchemy models but never expose the full ORM object —
this keeps the HTTP contract stable as the schema evolves.
"""
