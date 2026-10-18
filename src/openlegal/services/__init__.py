"""Application services: business logic that sits between the API and the ORM.

Keeping this layer thin and explicit lets the same logic be called from
HTTP handlers, UAPF host capability handlers, and CLI tools without
duplication.
"""
