"""Repositories: the only place raw SQL lives. Each module owns one table and
exposes small, intention-revealing functions so business logic never embeds
query strings. Every function takes an open ``sqlite3.Connection`` and leaves
transaction control (commit) to the caller unless noted."""
