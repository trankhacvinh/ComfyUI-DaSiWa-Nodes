"""Prompt-tagged REF2VA support for MiniMax H3 Director.

This wrapper keeps the original Director implementation intact.  For REF2VA it
optionally selects reference media from prompt @tags, then compiles those tags
to MiniMax's native <Picture N>/<Video N>/<Audio N> labels before delegating to
the existing Director.
"""

from __future__ import annotations

import copy
import json
import re

from .helper_logging import log_dasiwa
from .helper_minimax_h3_prompt_builder import (
    build_prompt,
    default_builder_state,
    migrate_legacy_prompt,
    normalize_ref_schema,
)
from .nodes_minimax_h3_director import MiniMaxH3Director as _BaseMiniMaxH3Director


_TAG_RE = re.compile(r"(?<![A-Za-z0-9_])@[A-Za-z0-9][A-Za-z0-9_.-]*")
_VALID_SELECTION_MODES = {"all", "tagged_only", "tagged_plus_untagged"}
_MEDIA_TYPES = {"image", "video", "audio"}


def normalize_reference_tag(value: str) -> str:
    """Normalize one tag to lower-case @name form; return '' when invalid."""
    text = str(value or "").strip()
    if not text:
        return ""
    if not text.startswith("@"):
        text = "@" + text
    return text.lower() if _TAG_RE.fullmatch(text) else ""


def extract_reference_tags(value) -> set[str]:
    """Extract normalized @tags from strings, arrays, or other simple values."""
    if isinstance(value, (list, tuple, set)):
        tags = set()
        for entry in value:
            tags.update(extract_reference_tags(entry))
        return tags
    return {match.lower() for match in _TAG_RE.findall(str(value or ""))}


def item_reference_tags(item: dict) -> set[str]:
    tags = extract_reference_tags(item.get("tags"))
    tags.update(extract_reference_tags(item.get("tag")))
    return tags


def _resolve_prompt_for_selection(
    mode: str,
    prompt: str,
    state: dict,
    builder_state,
    duration: int,
    external_prompt_overwrite,
) -> str:
    """Mirror Director prompt resolution closely enough to select references."""
    if isinstance(external_prompt_overwrite, str) and external_prompt_overwrite.strip():
        return external_prompt_overwrite

    # The browser Director stores the exact current builder prompt here.  Prefer
    # it when available because it is the same text the user previews in the UI.
    persisted = state.get("resolved_prompt")
    if isinstance(persisted, str) and persisted.strip():
        return persisted

    try:
        if isinstance(builder_state, str) and builder_state:
            builder = json.loads(builder_state)
        else:
            builder = state.get("builder_state", {})
    except (TypeError, json.JSONDecodeError):
        builder = {}
    if not isinstance(builder, dict):
        builder = {}

    merged = default_builder_state(mode)
    merged.update(builder)
    merged["ref"] = {**default_builder_state(mode)["ref"], **(builder.get("ref") or {})}
    normalize_ref_schema(merged["ref"])
    merged["mode"] = mode
    merged["duration"] = duration
    migrate_legacy_prompt(merged, state, prompt)
    return build_prompt(merged)


def _audio_lane_slot(item: dict, fallback: int) -> int:
    if item.get("type") == "video" and item.get("media_mode", "video") == "video_audio":
        return int(item.get("audioSlot", fallback))
    return int(item.get("slot", fallback))


def build_native_reference_labels(items: list[dict]) -> dict[str, list[str]]:
    """Return item-id -> native MiniMax labels after filtering/renumbering."""
    enabled = [item for item in items if item.get("enabled", True) and item.get("type") in _MEDIA_TYPES]

    images = sorted(
        (item for item in enabled if item.get("type") == "image"),
        key=lambda item: int(item.get("slot", 0)),
    )
    visual_videos = sorted(
        (
            item for item in enabled
            if item.get("type") == "video" and item.get("media_mode", "video") in {"video", "video_audio"}
        ),
        key=lambda item: int(item.get("slot", 0)),
    )

    audio_entries = []
    for index, item in enumerate(enabled):
        kind = item.get("type")
        video_mode = item.get("media_mode", "video")
        if kind == "audio" or (kind == "video" and video_mode in {"audio", "video_audio"}):
            audio_entries.append((_audio_lane_slot(item, index), index, item))
    audio_entries.sort(key=lambda entry: (entry[0], entry[1]))

    labels: dict[str, list[str]] = {}

    def key_for(item: dict, fallback: int) -> str:
        return str(item.get("id") or f"{item.get('type', 'ref')}:{item.get('slot', fallback)}")

    for number, item in enumerate(images, 1):
        labels.setdefault(key_for(item, number - 1), []).append(f"<Picture {number}>")
    for number, item in enumerate(visual_videos, 1):
        labels.setdefault(key_for(item, number - 1), []).append(f"<Video {number}>")
    for number, (_, _, item) in enumerate(audio_entries, 1):
        labels.setdefault(key_for(item, number - 1), []).append(f"<Audio {number}>")
    return labels


def _item_key(item: dict, fallback: int) -> str:
    return str(item.get("id") or f"{item.get('type', 'ref')}:{item.get('slot', fallback)}")


def select_tagged_reference_items(items: list[dict], prompt_text: str, selection_mode: str):
    """Filter media references and return (items, active_tags, available_tags)."""
    selection_mode = selection_mode if selection_mode in _VALID_SELECTION_MODES else "all"
    active_tags = extract_reference_tags(prompt_text)
    available_tags = set()
    for item in items:
        if item.get("type") in _MEDIA_TYPES and item.get("enabled", True):
            available_tags.update(item_reference_tags(item))

    if selection_mode == "all":
        return list(items), active_tags, available_tags

    selected = []
    media_before = 0
    media_after = 0
    for item in items:
        if item.get("type") not in _MEDIA_TYPES or not item.get("enabled", True):
            selected.append(item)
            continue

        media_before += 1
        tags = item_reference_tags(item)
        always_on = bool(item.get("always_on", False))
        matches = bool(tags & active_tags)
        untagged = not tags

        keep = always_on or matches
        if selection_mode == "tagged_plus_untagged":
            keep = keep or untagged

        if keep:
            selected.append(item)
            media_after += 1

    if media_before and not media_after:
        if active_tags:
            detail = ", ".join(sorted(active_tags))
            raise ValueError(
                "MiniMax H3 Director tagged references: no loaded reference matches "
                f"the active prompt tags ({detail}). Open 'Tagged References…' and assign matching tags."
            )
        raise ValueError(
            "MiniMax H3 Director tagged references: Prompt tags only is enabled, but the prompt contains no "
            "reference @tags and there are no Always-on references."
        )

    return selected, active_tags, available_tags


def compile_reference_tags(prompt_text: str, items: list[dict]) -> tuple[str, dict[str, str]]:
    """Compile recognized @tags to the native labels of the selected references."""
    labels_by_item = build_native_reference_labels(items)
    tag_labels: dict[str, list[str]] = {}

    for index, item in enumerate(items):
        if item.get("type") not in _MEDIA_TYPES or not item.get("enabled", True):
            continue
        labels = labels_by_item.get(_item_key(item, index), [])
        if not labels:
            continue
        for tag in item_reference_tags(item):
            bucket = tag_labels.setdefault(tag, [])
            for label in labels:
                if label not in bucket:
                    bucket.append(label)

    replacements = {tag: " and ".join(labels) for tag, labels in tag_labels.items() if labels}
    if not replacements:
        return prompt_text, {}

    def replace(match: re.Match) -> str:
        original = match.group(0)
        return replacements.get(original.lower(), original)

    return _TAG_RE.sub(replace, prompt_text), replacements


class MiniMaxH3Director(_BaseMiniMaxH3Director):
    """Backward-compatible Director with opt-in Ethan-style prompt tags."""

    def build_guide(
        self,
        mode,
        prompt,
        width,
        height,
        duration,
        ref_image_size,
        timeline_data,
        builder_state="",
        fl2va_model=None,
        ref2va_model=None,
        external_width_overwrite=None,
        external_height_overwrite=None,
        external_prompt_overwrite=None,
        frame_rate=24.0,
    ):
        if mode != "REF2VA":
            return super().build_guide(
                mode, prompt, width, height, duration, ref_image_size, timeline_data, builder_state,
                fl2va_model, ref2va_model, external_width_overwrite, external_height_overwrite,
                external_prompt_overwrite, frame_rate,
            )

        try:
            state = json.loads(timeline_data or "{}")
        except (TypeError, json.JSONDecodeError):
            # Preserve the base Director's canonical validation/error message.
            return super().build_guide(
                mode, prompt, width, height, duration, ref_image_size, timeline_data, builder_state,
                fl2va_model, ref2va_model, external_width_overwrite, external_height_overwrite,
                external_prompt_overwrite, frame_rate,
            )
        if not isinstance(state, dict):
            return super().build_guide(
                mode, prompt, width, height, duration, ref_image_size, timeline_data, builder_state,
                fl2va_model, ref2va_model, external_width_overwrite, external_height_overwrite,
                external_prompt_overwrite, frame_rate,
            )

        selection_mode = str(state.get("reference_selection") or "all")
        if selection_mode not in _VALID_SELECTION_MODES:
            selection_mode = "all"

        prompt_for_selection = _resolve_prompt_for_selection(
            mode, prompt, copy.deepcopy(state), builder_state, duration, external_prompt_overwrite,
        )
        all_items = list(state.get("items", []))
        has_tag_configuration = any(
            item_reference_tags(item) or bool(item.get("always_on", False))
            for item in all_items if isinstance(item, dict)
        )

        # Completely untouched old workflows keep the original code path.
        if selection_mode == "all" and not has_tag_configuration:
            return super().build_guide(
                mode, prompt, width, height, duration, ref_image_size, timeline_data, builder_state,
                fl2va_model, ref2va_model, external_width_overwrite, external_height_overwrite,
                external_prompt_overwrite, frame_rate,
            )

        filtered_items, active_tags, available_tags = select_tagged_reference_items(
            all_items, prompt_for_selection, selection_mode,
        )
        state["items"] = filtered_items

        compiled_prompt, replacements = compile_reference_tags(prompt_for_selection, filtered_items)
        unknown_tags = active_tags - available_tags
        if unknown_tags:
            log_dasiwa(
                "MiniMax H3 Director",
                "[WARNING] Prompt reference tag(s) have no loaded reference: " + ", ".join(sorted(unknown_tags)),
            )

        selected_media = [
            item for item in filtered_items
            if isinstance(item, dict) and item.get("enabled", True) and item.get("type") in _MEDIA_TYPES
        ]
        log_dasiwa(
            "MiniMax H3 Director",
            f"tagged_refs mode={selection_mode}; active={sorted(active_tags)}; "
            f"selected={len(selected_media)}/{sum(1 for item in all_items if isinstance(item, dict) and item.get('enabled', True) and item.get('type') in _MEDIA_TYPES)}; "
            f"compiled={replacements}",
        )

        result = super().build_guide(
            mode,
            prompt,
            width,
            height,
            duration,
            ref_image_size,
            json.dumps(state),
            builder_state,
            fl2va_model,
            ref2va_model,
            external_width_overwrite,
            external_height_overwrite,
            compiled_prompt,
            frame_rate,
        )

        guide = result[0]
        if isinstance(guide, dict):
            guide["tagged_references"] = {
                "selection_mode": selection_mode,
                "active_tags": sorted(active_tags),
                "available_tags": sorted(available_tags),
                "replacements": replacements,
                "selected_item_ids": [str(item.get("id")) for item in selected_media if item.get("id") is not None],
            }
        return result


NODE_CLASS_MAPPINGS = {"MiniMaxH3Director": MiniMaxH3Director}
NODE_DISPLAY_NAME_MAPPINGS = {"MiniMaxH3Director": "MiniMax H3 Director"}
