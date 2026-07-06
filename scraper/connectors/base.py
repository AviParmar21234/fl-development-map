"""Connector contract: each connector module exposes fetch(source) -> list[RawItem]."""
from dataclasses import dataclass


@dataclass
class RawItem:
    source_id: str
    jurisdiction: str
    county: str
    meeting_body: str
    meeting_date: str  # ISO date string YYYY-MM-DD
    title: str
    body_text: str
    link: str
