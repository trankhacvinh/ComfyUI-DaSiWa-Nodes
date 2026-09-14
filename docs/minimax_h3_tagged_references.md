# MiniMax H3 Director — Tagged References

This fork adds prompt-selected REF2VA references inspired by Ethan Fel's MiniMax H3 Context Loop while keeping the existing DaSiWa Director workflow and sampling graph.

## Open the tag editor

In ComfyUI, right-click **MiniMax H3 Director** and choose:

**🏷 Tagged References…**

The editor lists the image, video, and audio references currently loaded in the Director.

## Assign tags

Tags begin with `@` and may contain letters, numbers, `_`, `-`, and `.`.

Examples:

```text
@alice
@red_car
@office
@walking_motion
```

A reference may have more than one tag:

```text
@alice @main_character
```

Tags are case-insensitive. `@Alice` and `@alice` are the same tag.

## Reference selection modes

### All references (legacy behavior)

Every enabled REF2VA reference is sent to MiniMax, exactly like the original DaSiWa Director.

If tags are assigned, recognized tags in the prompt are still compiled to the corresponding native MiniMax labels.

This is the default for old workflows.

### Prompt tags only

Only references whose tags occur in the final Director prompt are sent to MiniMax.

Example loaded references:

```text
alice.png       @alice
bob.png         @bob
restaurant.png  @restaurant
walking.mp4     @walking
```

Prompt:

```text
@alice enters @restaurant.
```

Only `alice.png` and `restaurant.png` are conditioned into that generation.

This is the closest mode to Ethan's tagged-reference workflow.

### Prompt tags + untagged

Tagged references are selected by the prompt, while references with no tags remain active automatically.

This is useful for a global style/reference image that should always participate without requiring a tag in every prompt.

## Always on

Enable **Always on** for a reference if it must be included regardless of which tags occur in the prompt.

This works in both tag-selection modes.

## Native label compilation

MiniMax H3 natively understands reference labels such as:

```text
<Picture 1>
<Video 1>
<Audio 1>
```

The fork compiles friendly tags into those labels at queue time **after filtering and renumbering the selected references**.

For example, suppose the Director contains:

```text
Picture slot 1  @alice
Picture slot 2  @bob
Picture slot 3  @restaurant
```

and the prompt contains:

```text
@alice enters @restaurant.
```

`@bob` is not selected, so the two remaining references are renumbered and the prompt sent to native MiniMax becomes:

```text
<Picture 1> enters <Picture 2>.
```

You therefore do not need to maintain `Picture N` numbers manually when references are added, removed, or skipped.

A V+A video can compile to both its `<Video N>` and `<Audio N>` labels.

## One tag for multiple references

The same tag can be assigned to several assets. This is useful when multiple references jointly define one subject.

Example:

```text
face.png     @alice
outfit.png   @alice
```

Then:

```text
Preserve @alice.
```

can compile to:

```text
Preserve <Picture 1> and <Picture 2>.
```

## Unknown or missing tags

If the prompt contains a tag that has no loaded reference, DaSiWa logs a warning.

If **Prompt tags only** is enabled and no media reference matches the prompt, generation stops with a clear error rather than silently sending the wrong references.

## Backward compatibility

Existing workflows do not need to be changed.

If a workflow has no tag configuration and uses **All references**, the wrapper delegates directly to the original `MiniMaxH3Director` implementation.

To disable tag selection at any time, open **Tagged References…** and choose **All references (legacy behavior)**.

## Current reference-pack note

Tags and selection mode are persisted in the ComfyUI workflow JSON because they live in the Director timeline state. The original DaSiWa **Save Reference Pack** exporter predates this extension and does not yet include tag metadata in its portable reference-pack JSON. Workflow save/load is supported; portable tag-aware packs can be added separately later.
