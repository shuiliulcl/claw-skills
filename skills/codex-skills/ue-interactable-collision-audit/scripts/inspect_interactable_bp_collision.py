"""
Inspect collision and overlap settings for an Unreal Blueprint actor.

Run inside the Unreal Editor Python interpreter. Configure with globals before exec:

    BP_ASSET_PATH = r"/Game/Path/BP_Name.BP_Name"  # or a full .uasset path
    OUTPUT_DIR = r"F:\\project\\Temp\\CollisionAudit"  # optional
    OUTPUT_PATH = r"F:\\project\\Temp\\CollisionAudit\\report.md"  # optional
    SCAN_TEXT_REFERENCES = True

The script prints a compact summary and writes Markdown + JSON reports when an
output path or directory is provided.
"""

import json
import os
import re
from collections import Counter, defaultdict
from datetime import datetime

import unreal


BP_ASSET_PATH = globals().get("BP_ASSET_PATH", "")
OUTPUT_DIR = globals().get("OUTPUT_DIR", "")
OUTPUT_PATH = globals().get("OUTPUT_PATH", "")
SCAN_TEXT_REFERENCES = bool(globals().get("SCAN_TEXT_REFERENCES", True))
MAX_REFERENCE_HITS = int(globals().get("MAX_REFERENCE_HITS", 12))
MAX_SCAN_FILES = int(globals().get("MAX_SCAN_FILES", 20000))
TEXT_SCAN_ROOTS = globals().get("TEXT_SCAN_ROOTS", None)
SPAWN_Z = float(globals().get("SPAWN_Z", -100000.0))


def _enum_name(value):
    text = str(value)
    match = re.search(r"\.([A-Z][A-Z0-9_]+)", text)
    if match:
        return match.group(1)
    match = re.search(r"<[^.>]+\.([^:>]+)", text)
    if match:
        return match.group(1)
    return text.split(".")[-1].replace("'", "").replace(">", "")


def _safe_call(fn, default=None):
    try:
        return fn()
    except Exception:
        return default


def _safe_prop(obj, name, default=None):
    try:
        return obj.get_editor_property(name)
    except Exception:
        return default


def _name_list(values):
    if not values:
        return []
    return [str(v).strip('"') for v in values]


def _vector_dict(value):
    if value is None:
        return None
    return {
        "x": round(float(value.x), 4),
        "y": round(float(value.y), 4),
        "z": round(float(value.z), 4),
    }


def _rotator_dict(value):
    if value is None:
        return None
    return {
        "pitch": round(float(value.pitch), 4),
        "yaw": round(float(value.yaw), 4),
        "roll": round(float(value.roll), 4),
    }


def normalize_asset_path(asset_path):
    if not asset_path:
        raise RuntimeError("BP_ASSET_PATH is empty.")

    path = asset_path.strip().strip('"')
    path = path.replace("\\", "/")

    if path.startswith("/Game/"):
        path = path[:-7] if path.lower().endswith(".uasset") else path
        if "." not in os.path.basename(path):
            name = os.path.basename(path)
            path = path + "." + name
        return path

    if path.lower().endswith(".uasset"):
        project_content = unreal.Paths.convert_relative_path_to_full(
            unreal.Paths.project_content_dir()
        ).replace("\\", "/")
        lower_path = path.lower()
        lower_content = project_content.lower().rstrip("/") + "/"
        if lower_path.startswith(lower_content):
            rel = path[len(project_content.rstrip("/") + "/") : -7]
            package = "/Game/" + rel
            name = os.path.basename(rel)
            return package + "." + name

        marker = "/Content/"
        idx = lower_path.rfind(marker.lower())
        if idx >= 0:
            rel = path[idx + len(marker) : -7]
            package = "/Game/" + rel
            name = os.path.basename(rel)
            return package + "." + name

    return path


def load_blueprint(asset_ref):
    candidates = [asset_ref]
    if "." in os.path.basename(asset_ref):
        package = asset_ref.split(".")[0]
        candidates.append(package)
    else:
        name = os.path.basename(asset_ref)
        candidates.append(asset_ref + "." + name)

    for candidate in candidates:
        asset = unreal.EditorAssetLibrary.load_asset(candidate)
        if asset:
            return asset, candidate
    raise RuntimeError("Could not load Blueprint asset: {}".format(asset_ref))


def spawn_blueprint_actor(asset):
    subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    actor = subsystem.spawn_actor_from_object(
        asset,
        unreal.Vector(0.0, 0.0, SPAWN_Z),
        unreal.Rotator(0.0, 0.0, 0.0),
        transient=True,
    )
    if not actor:
        raise RuntimeError("Failed to spawn actor from Blueprint asset.")
    return subsystem, actor


def collision_responses(component):
    responses = {}
    for channel in unreal.CollisionChannel:
        response = _safe_call(lambda c=channel: component.get_collision_response_to_channel(c))
        if response is None:
            continue
        responses[_enum_name(channel)] = _enum_name(response)
    return responses


def shape_info(component):
    info = {}
    cls = component.get_class().get_name()
    if "CapsuleComponent" in cls:
        info["capsule_radius"] = _safe_call(component.get_scaled_capsule_radius)
        info["capsule_half_height"] = _safe_call(component.get_scaled_capsule_half_height)
    elif "SphereComponent" in cls:
        info["sphere_radius"] = _safe_call(component.get_scaled_sphere_radius)
    elif "BoxComponent" in cls:
        extent = _safe_call(component.get_scaled_box_extent)
        info["box_extent"] = _vector_dict(extent)
    elif "StaticMeshComponent" in cls:
        mesh = _safe_prop(component, "static_mesh")
        info["static_mesh"] = unreal.SystemLibrary.get_path_name(mesh) if mesh else None
    elif "SkeletalMeshComponent" in cls:
        mesh = _safe_prop(component, "skeletal_mesh_asset") or _safe_prop(component, "skeletal_mesh")
        info["skeletal_mesh"] = unreal.SystemLibrary.get_path_name(mesh) if mesh else None
    return info


def collect_component(component):
    is_primitive = isinstance(component, unreal.PrimitiveComponent)
    is_scene = isinstance(component, unreal.SceneComponent)

    data = {
        "name": component.get_name(),
        "class": component.get_class().get_name(),
        "is_primitive": bool(is_primitive),
        "tags": _name_list(_safe_prop(component, "component_tags", [])),
    }

    if is_scene:
        data["parent"] = _safe_call(lambda: component.get_attach_parent().get_name() if component.get_attach_parent() else None)
        data["relative_location"] = _vector_dict(_safe_prop(component, "relative_location"))
        data["relative_rotation"] = _rotator_dict(_safe_prop(component, "relative_rotation"))
        data["relative_scale3d"] = _vector_dict(_safe_prop(component, "relative_scale3d"))

    if is_primitive:
        data.update(
            {
                "collision_enabled": _enum_name(_safe_call(component.get_collision_enabled)),
                "collision_profile_name": str(_safe_call(component.get_collision_profile_name, "")),
                "object_type": _enum_name(_safe_call(component.get_collision_object_type)),
                "generate_overlap_events": bool(_safe_prop(component, "generate_overlap_events", False)),
                "can_character_step_up_on": _enum_name(_safe_prop(component, "can_character_step_up_on")),
                "hidden_in_game": bool(_safe_prop(component, "hidden_in_game", False)),
                "responses": collision_responses(component),
            }
        )
        data.update(shape_info(component))

    return data


def response_counts(component_data):
    responses = component_data.get("responses") or {}
    ignored_overlap_channels = {"ECC_WATER"}
    return {
        "overlap": sum(1 for r in responses.values() if r == "ECR_OVERLAP"),
        "meaningful_overlap": sum(
            1
            for channel, response in responses.items()
            if response == "ECR_OVERLAP" and channel not in ignored_overlap_channels
        ),
        "block": sum(1 for r in responses.values() if r == "ECR_BLOCK"),
        "ignore": sum(1 for r in responses.values() if r == "ECR_IGNORE"),
    }


def _counter_dict(counter):
    return {
        str(key): int(value)
        for key, value in sorted(counter.items(), key=lambda item: (-item[1], str(item[0])))
    }


def collision_statistics(components):
    primitives = [c for c in components if c.get("is_primitive")]
    stats = {
        "primitive_component_count": len(primitives),
        "collision_enabled": Counter(),
        "collision_profile_name": Counter(),
        "object_type": Counter(),
        "component_class": Counter(),
        "analysis_category": Counter(),
        "collision_necessity": Counter(),
        "overlap_necessity": Counter(),
        "generate_overlap_events": Counter(),
        "response_totals": Counter(),
        "non_ignore_response_by_channel": defaultdict(Counter),
        "component_flags": Counter(),
    }

    for component in primitives:
        stats["collision_enabled"][component.get("collision_enabled", "")] += 1
        stats["collision_profile_name"][component.get("collision_profile_name", "")] += 1
        stats["object_type"][component.get("object_type", "")] += 1
        stats["component_class"][component.get("class", "")] += 1
        stats["analysis_category"][component.get("analysis", {}).get("category", "")] += 1
        stats["collision_necessity"][component.get("analysis", {}).get("collision_necessity", "")] += 1
        stats["overlap_necessity"][component.get("analysis", {}).get("overlap_necessity", "")] += 1
        stats["generate_overlap_events"][str(bool(component.get("generate_overlap_events")))] += 1

        counts = response_counts(component)
        if component.get("generate_overlap_events"):
            stats["component_flags"]["generate_overlap_events_on"] += 1
        if component.get("collision_enabled") == "NO_COLLISION":
            stats["component_flags"]["no_collision"] += 1
        if component.get("collision_enabled") == "QUERY_ONLY":
            stats["component_flags"]["query_only"] += 1
        if component.get("collision_enabled") == "QUERY_AND_PHYSICS":
            stats["component_flags"]["query_and_physics"] += 1
        if counts["block"] > 0:
            stats["component_flags"]["has_block_response"] += 1
        if counts["meaningful_overlap"] > 0:
            stats["component_flags"]["has_meaningful_overlap_response"] += 1
        if counts["overlap"] > 0:
            stats["component_flags"]["has_any_overlap_response"] += 1

        for channel, response in (component.get("responses") or {}).items():
            stats["response_totals"][response] += 1
            if response != "ECR_IGNORE":
                stats["non_ignore_response_by_channel"][channel][response] += 1

    return {
        "primitive_component_count": stats["primitive_component_count"],
        "collision_enabled": _counter_dict(stats["collision_enabled"]),
        "collision_profile_name": _counter_dict(stats["collision_profile_name"]),
        "object_type": _counter_dict(stats["object_type"]),
        "component_class": _counter_dict(stats["component_class"]),
        "analysis_category": _counter_dict(stats["analysis_category"]),
        "collision_necessity": _counter_dict(stats["collision_necessity"]),
        "overlap_necessity": _counter_dict(stats["overlap_necessity"]),
        "generate_overlap_events": _counter_dict(stats["generate_overlap_events"]),
        "response_totals": _counter_dict(stats["response_totals"]),
        "component_flags": _counter_dict(stats["component_flags"]),
        "non_ignore_response_by_channel": {
            channel: _counter_dict(counter)
            for channel, counter in sorted(stats["non_ignore_response_by_channel"].items())
        },
    }


def project_search_roots():
    if TEXT_SCAN_ROOTS:
        return [r for r in TEXT_SCAN_ROOTS if os.path.isdir(r)]

    project_dir = unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir())
    roots = [
        os.path.join(project_dir, "Content", "Script"),
        os.path.join(project_dir, "Source"),
    ]
    return [r for r in roots if os.path.isdir(r)]


def scan_text_references(components):
    terms = {}
    for component in components:
        names = [component["name"]] + component.get("tags", [])
        for term in names:
            if term and len(term) >= 3:
                terms.setdefault(term, [])

    if not terms:
        return {}

    allowed_exts = {".lua", ".cpp", ".h", ".hpp", ".c", ".cs", ".py", ".ini", ".json"}
    term_lookup = {term: term for term in terms}
    combined = re.compile("|".join(re.escape(term) for term in sorted(terms, key=len, reverse=True)))
    scanned_files = 0

    for root in project_search_roots():
        for dirpath, _, filenames in os.walk(root):
            for filename in filenames:
                if scanned_files >= MAX_SCAN_FILES:
                    return terms
                ext = os.path.splitext(filename)[1].lower()
                if ext not in allowed_exts:
                    continue
                path = os.path.join(dirpath, filename)
                scanned_files += 1
                try:
                    with open(path, "r", encoding="utf-8", errors="ignore") as handle:
                        for lineno, line in enumerate(handle, 1):
                            if not combined.search(line):
                                continue
                            for match in combined.finditer(line):
                                term = term_lookup.get(match.group(0))
                                if not term:
                                    continue
                                if len(terms[term]) >= MAX_REFERENCE_HITS:
                                    continue
                                terms[term].append(
                                    {
                                        "file": path.replace("\\", "/"),
                                        "line": lineno,
                                        "text": line.strip()[:220],
                                    }
                                )
                except Exception:
                    continue
    return terms


def classify_component(component, references):
    if not component.get("is_primitive"):
        return {
            "category": "non_primitive",
            "overlap_necessity": "n/a",
            "collision_necessity": "n/a",
            "reasons": ["No PrimitiveComponent collision settings."],
        }

    name = component["name"]
    tags = component.get("tags", [])
    lower = " ".join([name] + tags).lower()
    counts = response_counts(component)
    collision_enabled = component.get("collision_enabled")
    generate_overlap = component.get("generate_overlap_events")
    has_name_refs = bool(references.get(name))
    has_tag_refs = any(references.get(tag) for tag in tags)
    has_refs = has_name_refs or has_tag_refs
    has_overlap_response = counts["meaningful_overlap"] > 0
    has_block_response = counts["block"] > 0

    reasons = []
    category = "needs_review"
    overlap_need = "needs_review"
    collision_need = "needs_review"

    if collision_enabled == "NO_COLLISION":
        category = "disabled"
        collision_need = "disabled"
        overlap_need = "unnecessary"
        reasons.append("Collision is disabled; overlap generation has no runtime effect.")
    elif "targetlocation" in lower or "jumptar" in lower or ("target" in lower and "location" in lower):
        category = "marker"
        collision_need = "probably_unnecessary"
        overlap_need = "probably_unnecessary"
        reasons.append("Looks like a marker/target point component.")
        if has_tag_refs:
            reasons.append("Tag is referenced by code; keep the component/tag unless code is changed.")
        if "CapsuleComponent" in component["class"]:
            reasons.append("If code searches UCapsuleComponent by tag, keep CapsuleComponent type but disable collision.")
    elif generate_overlap and has_overlap_response and (
        "trigger" in lower
        or "detect" in lower
        or "overlap" in lower
        or "weight" in lower
        or has_refs
    ):
        category = "overlap_trigger"
        overlap_need = "probably_required"
        collision_need = "query_overlap"
        reasons.append("Configured as overlap and has trigger-like name, tag, or text references.")
    elif has_block_response and not has_overlap_response:
        category = "blocking_proxy"
        collision_need = "probably_required" if ("collision" in lower or has_refs or component.get("hidden_in_game")) else "needs_review"
        overlap_need = "probably_unnecessary"
        reasons.append("Blocks channels but has no overlap responses.")
    elif has_overlap_response and not generate_overlap:
        category = "overlap_response_without_events"
        overlap_need = "disabled_or_misconfigured"
        collision_need = "needs_review"
        reasons.append("Has overlap responses but Generate Overlap Events is false.")
    elif generate_overlap and not has_overlap_response:
        category = "overlap_events_redundant"
        overlap_need = "probably_unnecessary"
        collision_need = "needs_review"
        reasons.append("Generate Overlap Events is true but no channel response is Overlap.")
    elif has_overlap_response:
        category = "overlap_needs_review"
        overlap_need = "needs_review"
        collision_need = "query_overlap"
        reasons.append("Has overlap responses but no clear text evidence of use.")
    else:
        reasons.append("No decisive heuristic matched.")

    if generate_overlap and overlap_need in {"probably_unnecessary", "unnecessary"}:
        reasons.append("Candidate optimization: turn off Generate Overlap Events.")

    if has_refs:
        reasons.append("Found text references for component name or tags.")
    else:
        reasons.append("No text references found; Blueprint graph references may still exist.")

    return {
        "category": category,
        "overlap_necessity": overlap_need,
        "collision_necessity": collision_need,
        "reasons": reasons,
    }


def build_report(asset_ref, loaded_ref, actor, components, references):
    primitive_count = sum(1 for c in components if c.get("is_primitive"))
    overlap_on = [
        c
        for c in components
        if c.get("is_primitive") and c.get("generate_overlap_events")
    ]
    candidates = [
        c
        for c in components
        if c.get("analysis", {}).get("overlap_necessity")
        in ("probably_unnecessary", "unnecessary")
        and c.get("generate_overlap_events")
    ]
    required = [
        c
        for c in components
        if c.get("analysis", {}).get("overlap_necessity") == "probably_required"
    ]

    collision_stats = collision_statistics(components)

    return {
        "asset_ref": asset_ref,
        "loaded_ref": loaded_ref,
        "actor_class": actor.get_class().get_name(),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "summary": {
            "component_count": len(components),
            "primitive_component_count": primitive_count,
            "generate_overlap_events_on_count": len(overlap_on),
            "overlap_can_turn_off_candidate_count": len(candidates),
            "overlap_probably_required_count": len(required),
            "collision_profile_count": len(collision_stats["collision_profile_name"]),
            "collision_enabled_modes": collision_stats["collision_enabled"],
        },
        "collision_statistics": collision_stats,
        "components": components,
        "references": references,
    }


def append_count_table(lines, title, values):
    if not values:
        return
    lines.append("### {}".format(title))
    lines.append("")
    lines.append("| Value | Count |")
    lines.append("| --- | ---: |")
    for value, count in values.items():
        lines.append("| `{}` | {} |".format(value, count))
    lines.append("")


def append_collision_statistics(lines, stats):
    lines.append("## Collision Statistics")
    lines.append("")
    lines.append("- Primitive components: {}".format(stats["primitive_component_count"]))
    flags = stats.get("component_flags", {})
    lines.append("- QueryOnly: {}".format(flags.get("query_only", 0)))
    lines.append("- QueryAndPhysics: {}".format(flags.get("query_and_physics", 0)))
    lines.append("- NoCollision: {}".format(flags.get("no_collision", 0)))
    lines.append("- Components with block response: {}".format(flags.get("has_block_response", 0)))
    lines.append("- Components with meaningful overlap response: {}".format(flags.get("has_meaningful_overlap_response", 0)))
    lines.append("- Components with any overlap response: {}".format(flags.get("has_any_overlap_response", 0)))
    lines.append("")

    append_count_table(lines, "Collision Enabled", stats.get("collision_enabled", {}))
    append_count_table(lines, "Collision Profiles", stats.get("collision_profile_name", {}))
    append_count_table(lines, "Object Types", stats.get("object_type", {}))
    append_count_table(lines, "Component Classes", stats.get("component_class", {}))
    append_count_table(lines, "Analysis Categories", stats.get("analysis_category", {}))
    append_count_table(lines, "Collision Necessity", stats.get("collision_necessity", {}))
    append_count_table(lines, "Overlap Necessity", stats.get("overlap_necessity", {}))
    append_count_table(lines, "Response Totals", stats.get("response_totals", {}))

    channel_stats = stats.get("non_ignore_response_by_channel", {})
    if channel_stats:
        lines.append("### Non-Ignore Responses By Channel")
        lines.append("")
        lines.append("| Channel | Block | Overlap | Ignore | Other |")
        lines.append("| --- | ---: | ---: | ---: | ---: |")
        for channel, counts in channel_stats.items():
            block = counts.get("ECR_BLOCK", 0)
            overlap = counts.get("ECR_OVERLAP", 0)
            ignore = counts.get("ECR_IGNORE", 0)
            other = sum(v for k, v in counts.items() if k not in {"ECR_BLOCK", "ECR_OVERLAP", "ECR_IGNORE"})
            lines.append("| `{}` | {} | {} | {} | {} |".format(channel, block, overlap, ignore, other))
        lines.append("")


def markdown_report(report):
    lines = []
    summary = report["summary"]
    lines.append("# Interactable Collision Audit")
    lines.append("")
    lines.append("- Asset: `{}`".format(report["loaded_ref"]))
    lines.append("- Actor class: `{}`".format(report["actor_class"]))
    lines.append("- Generated: `{}`".format(report["generated_at"]))
    lines.append("- Components: {} total, {} primitive".format(summary["component_count"], summary["primitive_component_count"]))
    lines.append("- Generate Overlap Events ON: {}".format(summary["generate_overlap_events_on_count"]))
    lines.append("- Overlap turn-off candidates: {}".format(summary["overlap_can_turn_off_candidate_count"]))
    lines.append("- Overlap probably required: {}".format(summary["overlap_probably_required_count"]))
    lines.append("- Collision profiles: {}".format(summary["collision_profile_count"]))
    lines.append("- Collision enabled modes: `{}`".format(summary["collision_enabled_modes"]))
    lines.append("")

    append_collision_statistics(lines, report["collision_statistics"])

    groups = [
        ("Overlap Can Probably Turn Off", lambda c: c.get("generate_overlap_events") and c["analysis"]["overlap_necessity"] in ("probably_unnecessary", "unnecessary")),
        ("Overlap Probably Required", lambda c: c["analysis"]["overlap_necessity"] == "probably_required"),
        ("Blocking / Collision Proxies", lambda c: c["analysis"]["category"] == "blocking_proxy"),
        ("Markers / Target Points", lambda c: c["analysis"]["category"] == "marker"),
        ("Needs Review", lambda c: c["analysis"]["overlap_necessity"] in ("needs_review", "disabled_or_misconfigured")),
    ]

    for title, pred in groups:
        items = [c for c in report["components"] if c.get("is_primitive") and pred(c)]
        if not items:
            continue
        lines.append("## {}".format(title))
        lines.append("")
        for c in items:
            counts = response_counts(c)
            lines.append("### `{}` ({})".format(c["name"], c["class"]))
            lines.append("")
            lines.append("- Category: `{}`".format(c["analysis"]["category"]))
            lines.append("- Collision: `{}` / profile `{}` / object `{}`".format(c.get("collision_enabled"), c.get("collision_profile_name"), c.get("object_type")))
            lines.append("- Generate Overlap Events: `{}`".format(c.get("generate_overlap_events")))
            lines.append(
                "- Responses: overlap {} (meaningful {}), block {}, ignore {}".format(
                    counts["overlap"],
                    counts["meaningful_overlap"],
                    counts["block"],
                    counts["ignore"],
                )
            )
            lines.append("- Tags: `{}`".format(", ".join(c.get("tags") or []) or ""))
            if c.get("relative_location"):
                lines.append("- Relative location: `{}`".format(c["relative_location"]))
            if c.get("static_mesh"):
                lines.append("- Static mesh: `{}`".format(c["static_mesh"]))
            if c.get("skeletal_mesh"):
                lines.append("- Skeletal mesh: `{}`".format(c["skeletal_mesh"]))
            lines.append("- Overlap necessity: `{}`".format(c["analysis"]["overlap_necessity"]))
            lines.append("- Collision necessity: `{}`".format(c["analysis"]["collision_necessity"]))
            for reason in c["analysis"]["reasons"]:
                lines.append("  - {}".format(reason))
            ref_terms = [c["name"]] + c.get("tags", [])
            ref_hits = []
            for term in ref_terms:
                ref_hits.extend(report["references"].get(term, []))
            if ref_hits:
                lines.append("- Reference examples:")
                for hit in ref_hits[:5]:
                    lines.append("  - `{}`:{} `{}`".format(hit["file"], hit["line"], hit["text"]))
            lines.append("")

    lines.append("## All Primitive Components")
    lines.append("")
    lines.append("| Component | Class | Collision | Profile | OverlapEvents | Category | Overlap Need |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- |")
    for c in [x for x in report["components"] if x.get("is_primitive")]:
        lines.append(
            "| `{}` | `{}` | `{}` | `{}` | `{}` | `{}` | `{}` |".format(
                c["name"],
                c["class"],
                c.get("collision_enabled"),
                c.get("collision_profile_name"),
                c.get("generate_overlap_events"),
                c["analysis"]["category"],
                c["analysis"]["overlap_necessity"],
            )
        )
    lines.append("")
    return "\n".join(lines)


def default_output_path(asset_ref):
    project_dir = unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir())
    out_dir = OUTPUT_DIR or os.path.join(project_dir, "Saved", "CollisionAudit")
    package = asset_ref.split(".")[0]
    name = os.path.basename(package)
    return os.path.join(out_dir, "{}_collision_audit.md".format(name))


def write_outputs(report):
    md = markdown_report(report)
    path = OUTPUT_PATH or default_output_path(report["loaded_ref"])
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(md)

    json_path = os.path.splitext(path)[0] + ".json"
    with open(json_path, "w", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)

    return path, json_path


def run_audit(bp_asset_path):
    asset_ref = normalize_asset_path(bp_asset_path)
    asset, loaded_ref = load_blueprint(asset_ref)
    subsystem, actor = spawn_blueprint_actor(asset)
    try:
        components = [
            collect_component(component)
            for component in actor.get_components_by_class(unreal.ActorComponent)
        ]
        references = scan_text_references(components) if SCAN_TEXT_REFERENCES else {}
        for component in components:
            component["analysis"] = classify_component(component, references)
        return build_report(asset_ref, loaded_ref, actor, components, references)
    finally:
        subsystem.destroy_actor(actor)


report = run_audit(BP_ASSET_PATH)
md_path, json_path = write_outputs(report)
summary = report["summary"]

print("Collision audit complete")
print("Asset:", report["loaded_ref"])
print("Markdown:", md_path)
print("JSON:", json_path)
print("Summary:", json.dumps(summary, ensure_ascii=False))

turn_off = [
    c["name"]
    for c in report["components"]
    if c.get("is_primitive")
    and c.get("generate_overlap_events")
    and c["analysis"]["overlap_necessity"] in ("probably_unnecessary", "unnecessary")
]
required = [
    c["name"]
    for c in report["components"]
    if c.get("is_primitive")
    and c["analysis"]["overlap_necessity"] == "probably_required"
]

print("Overlap turn-off candidates:", ", ".join(turn_off) if turn_off else "(none)")
print("Overlap probably required:", ", ".join(required) if required else "(none)")
