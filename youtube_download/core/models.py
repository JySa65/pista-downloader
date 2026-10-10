from dataclasses import dataclass


@dataclass
class Track:
    id: str
    title: str
    channel: str
    duration: float | None
    url: str
    thumbnail: str | None
    playlist: str = ""  # source playlist/mix title; empty for single videos
