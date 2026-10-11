from dataclasses import dataclass, field


@dataclass
class Track:
    id: str
    title: str
    channel: str
    duration: float | None
    url: str
    thumbnail: str | None
    playlist: str = ""  # source playlist/mix title; empty for single videos
    video_sizes: dict[str, int] = field(default_factory=dict)  # MP4 bytes per resolution, when extracted
