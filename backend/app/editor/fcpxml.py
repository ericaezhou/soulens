"""
Generates a Final Cut Pro XML (fcpxml 1.9) process file from the precision cuts.

Each cut is a separate clip on the timeline referencing its ORIGINAL source file
with exact in/out timecodes — not the rendered selects.mp4. This means the creator
can open the file in Final Cut Pro, extend any cut back into the original footage,
delete cuts, or reorder them.

Opens in: Final Cut Pro. Compatible importers exist for DaVinci Resolve and Premiere Pro.
"""
from pathlib import Path
from xml.etree.ElementTree import Element, SubElement, ElementTree, indent


def _to_fcp_time(seconds: float) -> str:
    tb = 90000
    frames = round(seconds * tb)
    return f"{frames}/{tb}s"


def generate_fcpxml(
    cuts: list[dict],
    output_path: str,
    project_name: str = "auto-edit",
    caption_plan: list[dict] | None = None,
) -> str:
    """
    cuts: list of {"clip_path", "start_s", "end_s", "duration_s"}
          Each entry is one Phase 3 precision cut referencing its original source clip.
    output_path: where to write the .fcpxml file.
    """
    root = Element("fcpxml", version="1.9")
    resources = SubElement(root, "resources")

    SubElement(resources, "format",
        id="r1",
        name="FFVideoFormat1080p30",
        frameDuration="1001/30030s",
        width="1080",
        height="1920",
    )

    # One asset per unique source clip
    seen: dict[str, str] = {}  # clip_path → asset id
    for cut in cuts:
        cp = cut["clip_path"]
        if cp in seen:
            continue
        asset_id = f"r{len(seen) + 2}"
        seen[cp] = asset_id
        # Use just the filename — ZIP bundle workflow means clips are co-located with FCPXML.
        # DaVinci will ask to locate the folder once and auto-relinks all clips.
        src = f"file://{Path(cp).name}"
        SubElement(resources, "asset",
            id=asset_id,
            name=Path(cp).stem,
            src=src,
            start="0s",
            duration="0/90000s",  # FCP reads actual duration from the file
            hasVideo="1",
            hasAudio="1",
            audioSources="1",
            audioChannels="2",
            audioRate="48000",
        )

    library = SubElement(root, "library")
    event = SubElement(library, "event", name="auto-edit")
    project = SubElement(event, "project", name=project_name)

    total_duration = sum(c["duration_s"] for c in cuts)
    sequence = SubElement(project, "sequence",
        duration=_to_fcp_time(total_duration),
        format="r1",
        tcStart="0s",
        tcFormat="NDF",
        audioLayout="stereo",
        audioRate="48000",
    )

    spine = SubElement(sequence, "spine")

    timeline_offset = 0.0
    for i, cut in enumerate(cuts):
        asset_id = seen[cut["clip_path"]]
        dur = cut["duration_s"]
        start_in_source = cut["start_s"]

        clip_el = SubElement(spine, "clip",
            name=f"{Path(cut['clip_path']).stem} · cut {i+1}",
            ref=asset_id,
            offset=_to_fcp_time(timeline_offset),
            duration=_to_fcp_time(dur),
            start=_to_fcp_time(start_in_source),
        )

        timeline_offset += dur

    if caption_plan:
        _add_captions(spine, caption_plan)

    tree = ElementTree(root)
    indent(tree, space="  ")
    tree.write(output_path, encoding="unicode", xml_declaration=True)
    return output_path


def _add_captions(spine: Element, caption_plan: list[dict]) -> None:
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
        p = SubElement(title, "param", name="Text")
        SubElement(p, "value").text = text

        positions = {"lower_third": "0 -0.35", "upper_third": "0 0.35", "center": "0 0"}
        pos_el = SubElement(title, "param", name="Position")
        SubElement(pos_el, "value").text = positions.get(placement, "0 -0.35")
