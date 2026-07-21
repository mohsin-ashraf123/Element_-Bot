"""Deterministic core — pure business logic with zero I/O.

Everything in this package is a pure function of its inputs: no database,
no network, no clock reads (time is always passed in). This makes the core
fully unit-testable and reproducible, exactly as required by the PRD/RULES.
"""
