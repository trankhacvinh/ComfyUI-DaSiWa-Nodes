import json

import pytest

from nodes.nodes_minimax_h3_director_tagged import (
    MiniMaxH3Director,
    build_native_reference_labels,
    compile_reference_tags,
    extract_reference_tags,
    select_tagged_reference_items,
)


def _image(item_id, slot, value, tags=None, **extra):
    item = {"id": item_id, "type": "image", "slot": slot, "value": value, "enabled": True}
    if tags is not None:
        item["tags"] = tags
    item.update(extra)
    return item


def test_extract_reference_tags_is_case_insensitive_and_deduplicated():
    assert extract_reference_tags("@Alice meets @CAR, then @alice returns") == {"@alice", "@car"}


def test_tagged_only_filters_media_but_keeps_non_media_items():
    items = [
        _image("alice", 0, "alice.png", ["@alice"]),
        _image("bob", 1, "bob.png", ["@bob"]),
        {"id": "note", "type": "text", "value": "prompt helper", "enabled": True},
    ]

    selected, active, available = select_tagged_reference_items(items, "@alice walks in", "tagged_only")

    assert active == {"@alice"}
    assert available == {"@alice", "@bob"}
    assert [item["id"] for item in selected] == ["alice", "note"]


def test_tagged_plus_untagged_keeps_untagged_reference():
    items = [
        _image("alice", 0, "alice.png", ["@alice"]),
        _image("room", 1, "room.png"),
        _image("bob", 2, "bob.png", ["@bob"]),
    ]

    selected, *_ = select_tagged_reference_items(items, "@alice enters", "tagged_plus_untagged")
    assert [item["id"] for item in selected] == ["alice", "room"]


def test_always_on_reference_survives_tagged_only_without_its_tag_in_prompt():
    items = [
        _image("style", 0, "style.png", ["@style"], always_on=True),
        _image("alice", 1, "alice.png", ["@alice"]),
    ]

    selected, *_ = select_tagged_reference_items(items, "@alice smiles", "tagged_only")
    assert [item["id"] for item in selected] == ["style", "alice"]


def test_tagged_only_fails_clearly_when_nothing_matches():
    items = [_image("alice", 0, "alice.png", ["@alice"])]
    with pytest.raises(ValueError, match="no loaded reference matches"):
        select_tagged_reference_items(items, "@bob walks", "tagged_only")


def test_compiler_renumbers_selected_images_and_replaces_tags():
    items = [
        _image("alice", 4, "alice.png", ["@alice"]),
        _image("room", 8, "room.png", ["@room"]),
    ]

    compiled, replacements = compile_reference_tags("@alice enters @room. @ALICE sits.", items)

    assert replacements == {"@alice": "<Picture 1>", "@room": "<Picture 2>"}
    assert compiled == "<Picture 1> enters <Picture 2>. <Picture 1> sits."


def test_same_tag_can_point_to_multiple_native_references():
    items = [
        _image("face", 0, "face.png", ["@alice"]),
        _image("costume", 1, "costume.png", ["@alice"]),
    ]

    compiled, replacements = compile_reference_tags("Preserve @alice.", items)
    assert replacements["@alice"] == "<Picture 1> and <Picture 2>"
    assert compiled == "Preserve <Picture 1> and <Picture 2>."


def test_video_audio_reference_gets_video_and_audio_native_labels():
    items = [
        {"id": "motion", "type": "video", "slot": 0, "audioSlot": 1, "media_mode": "video_audio", "value": "motion.mp4", "tags": ["@motion"], "enabled": True},
        {"id": "voice", "type": "audio", "slot": 0, "value": "voice.wav", "tags": ["@voice"], "enabled": True},
    ]

    labels = build_native_reference_labels(items)
    assert labels["motion"] == ["<Video 1>", "<Audio 2>"]
    assert labels["voice"] == ["<Audio 1>"]


def test_director_integration_filters_and_compiles_before_native_guide():
    state = {
        "reference_selection": "tagged_only",
        "items": [
            _image("alice", 0, "alice.png", ["@alice"]),
            _image("bob", 1, "bob.png", ["@bob"]),
            _image("room", 2, "room.png", ["@room"]),
        ],
    }

    guide, _, resolved, *_ = MiniMaxH3Director().build_guide(
        "REF2VA",
        "",
        1344,
        768,
        5,
        "match",
        json.dumps(state),
        external_prompt_overwrite="subject_definitions:\n@alice is the woman. @room is the location.",
    )

    assert guide["ref_images"] == {"ref_image_1": "alice.png", "ref_image_2": "room.png"}
    assert "bob.png" not in guide["ref_images"].values()
    assert resolved == "subject_definitions:\n<Picture 1> is the woman. <Picture 2> is the location."
    assert guide["tagged_references"]["selection_mode"] == "tagged_only"
    assert guide["tagged_references"]["selected_item_ids"] == ["alice", "room"]


def test_legacy_ref2va_without_tag_configuration_keeps_original_behavior():
    state = {"items": [_image("one", 0, "one.png"), _image("two", 1, "two.png")]}

    guide, *_ = MiniMaxH3Director().build_guide(
        "REF2VA", "", 1344, 768, 5, "match", json.dumps(state), external_prompt_overwrite="plain prompt"
    )

    assert guide["ref_images"] == {"ref_image_1": "one.png", "ref_image_2": "two.png"}
    assert "tagged_references" not in guide
