"""
Generates a Final Cut Pro XML (fcpxml 1.9) file from an edit plan.
Opens in: Final Cut Pro, iMovie, DaVinci Resolve, Premiere Pro (via XML import).
"""
import math
from pathlib import Path
from xml.etree.ElementTree import Element, SubElement, ElementTree, indent


def _to_fcp_time(seconds: float) -> str:
    """Convert seconds to FCP rational time string (e.g. '90000/90000s')."""
    # FCP uses 90000 as the common timebase
    tb = 90000
    frames = round(seconds * tb)
    return f"{frames}/{tb}s"


def generate_fcpxml(
    clips: list[dict],
    source_path: str,
    output_path: str,
    project_name: str = "auto-edit",
    caption_plan: list[dict] | None = None,
) -> str:
    """
    clips: list of {"start": float, "end": float, "duration": float}
    source_path: absolute path to the source footage file
    output_path: where to write the .fcpxml file
    caption_plan: optional list of {"timestamp_s", "duration_s", "text", "placement"}
    Returns the output path.
    """
    source = Path(source_path)

    root = Element("fcpxml", version="1.9")

    # Resources
    resources = SubElement(root, "resources")

    # Format (1080p 30fps — we'll probe and adjust if needed)
    fmt = SubElement(resources, "format",
        id="r1",
        name="FFVideoFormat1080p30",
        frameDuration="1001/30030s",
        width="1080",
        height="1920",  # Vertical for Reels
    )

    # Asset — the source footage
    total_duration = sum(c["duration"] for c in clips)
    asset = SubElement(resources, "asset",
        id="r2",
        name=source.stem,
        src=source.as_uri(),
        start="0s",
        duration=_to_fcp_time(total_duration),
        hasVideo="1",
        hasAudio="1",
        audioSources="1",
        audioChannels="2",
        audioRate="48000",
    )

    # Library > Event > Project > Sequence > Spine
    library = SubElement(root, "library")
    event = SubElement(library, "event", name="auto-edit")
    project = SubElement(event, "project", name=project_name)

    sequence = SubElement(project, "sequence",
        duration=_to_fcp_time(total_duration),
        format="r1",
        tcStart="0s",
        tcFormat="NDF",
        audioLayout="stereo",
        audioRate="48000",
    )

    spine = SubElement(sequence, "spine")

    # Add each clip to the spine
    timeline_offset = 0.0
    for i, clip in enumerate(clips):
        start = clip["start"]
        duration = clip["duration"]

        clip_el = SubElement(spine, "clip",
            name=f"clip_{i+1}",
            ref="r2",
            offset=_to_fcp_time(timeline_offset),
            duration=_to_fcp_time(duration),
            start=_to_fcp_time(start),
        )

        # Color correction as built-in effect
        color = clip.get("color", {})
        if color:
            _add_color_correction(clip_el, color)

        timeline_offset += duration

    # Add caption titles if provided
    if caption_plan:
        _add_captions(spine, caption_plan)

    # Write file
    tree = ElementTree(root)
    indent(tree, space="  ")
    tree.write(output_path, encoding="unicode", xml_declaration=True)

    return output_path


def _add_color_correction(clip_el: Element, color: dict) -> None:
    """Add FCP color board adjustment to a clip."""
    filter_video = SubElement(clip_el, "filter-video")
    effect = SubElement(filter_video, "effect",
        name="Color Board",
        uid=".../Effects.localized/Color.localized/Color Board.localized/Color Board.moef",
    )

    # Map our eq params to FCP Color Board values
    brightness = color.get("brightness", 0)   # -0.5 to 0.5
    saturation = color.get("saturation", 1.0) # 0 to 3
    contrast = color.get("contrast", 1.0)

    params = [
        ("masterBrightness", brightness * 0.4),
        ("masterSaturation", (saturation - 1.0) * 0.5),
        ("masterContrast", (contrast - 1.0) * 0.3),
    ]
    for name, value in params:
        p = SubElement(effect, "param", name=name)
        SubElement(p, "value").text = str(round(value, 4))


def _add_captions(spine: Element, caption_plan: list[dict]) -> None:
    """Add title elements for text overlays."""
    for cap in caption_plan:
        ts = cap.get("timestamp_s", 0)
        dur = cap.get("duration_s", 2.0)
        text = cap.get("text", "")
        placement = cap.get("placement", "lower_third")

        if not text:
            continue

        title = SubElement(spine, "title",
            name=f"Caption: {text[:20]}",
            lane="1",
            offset=_to_fcp_time(ts),
            duration=_to_fcp_time(dur),
            start=_to_fcp_time(ts),
        )

        # Text param
        p = SubElement(title, "param", name="Text")
        SubElement(p, "value").text = text

        # Position based on placement
        positions = {
            "lower_third": "0 -0.35",
            "upper_third": "0 0.35",
            "center": "0 0",
        }
        pos = SubElement(title, "param", name="Position")
        SubElement(pos, "value").text = positions.get(placement, "0 -0.35")
