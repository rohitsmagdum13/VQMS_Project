"""Module: utils/validation.py

Input validation helpers for VQMS.

Functions in this module validate data at system boundaries —
user input, API responses, and external service payloads.
Internal data that has already been validated by Pydantic models
does not need re-validation here.

TODO: Add validation functions as needed in later phases.
"""

from __future__ import annotations
