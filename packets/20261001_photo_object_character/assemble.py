#!/usr/bin/env python3
"""Season packet: photo → object/character procedural knowledge.

Source-bound reconstruction of Anil-matcha/game-creator @ 4e64b83 and four
sibling repos. Remote APIs are planned, not called. Likeness web-fetch nodes
exist in the donor tree and are HELD by default.

Run: python3 assemble.py
Writes the wiki, behavior tree, OKF-C capsule, JSONL cards, SQLite store,
and a BM25 readout. Exits non-zero if a local invariant fails.
"""

from __future__ import annotations

import hashlib
import json
import math
import sqlite3
import textwrap
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
NOW = "2026-10-01T22:30:00Z"
CHAIN = "eve-photo-object-character-2026-10-01"

PINS = {
    "game-creator": {
        "owner": "Anil-matcha",
        "sha": "4e64b83b5fe400b34ad3a484d9b4a6090b26d512",
        "committed": "2026-05-25T14:02:21-04:00",
        "license_note": "README declares MIT. A raw LICENSE fetch at this SHA returned HTTP 404; do not treat the badge as a copied license file.",
        "role": "executable donor for photo-composite characters and image/text-to-3D objects",
    },
    "awesome-ai-game-generation": {
        "owner": "Anil-matcha",
        "sha": "10fac24a9cf22bb6149cee7d8edf2d3bee4e5fa6",
        "committed": "2026-09-02T20:54:20+0530",
        "license_note": "CC0 1.0 Universal (LICENSE file present).",
        "role": "catalog. Not an implementation of photo-to-character.",
    },
    "awesome-gpt-6-astra": {
        "owner": "Anil-matcha",
        "sha": "5f6ccbaf684f09e7d87051efdd98c0da03317f3e",
        "committed": "2026-09-20T10:39:49+0530",
        "license_note": "MIT (LICENSE file present). Entries are anecdotal SOURCE_CLAIMs.",
        "role": "catalog of reported Astra workflows, including image-then-3D.",
    },
    "awesome-vibecoded-saas": {
        "owner": "Anil-matcha",
        "sha": "a619af1f0ca938ef78b9fbf7558a45f6c5b31aea",
        "committed": "2026-09-18T01:34:26+0530",
        "license_note": "MIT (LICENSE file present).",
        "role": "catalog. Points at image studios, not a photo-to-mesh algorithm.",
    },
    "loreweaver": {
        "owner": "Anil-matcha",
        "sha": "f61aa09a416d0fd3c28212ab99180b168c1f9ecd",
        "committed": "2026-09-05T00:11:38+0800",
        "license_note": "MIT (LICENSE file present). README badges and install docs point at 1A7432/loreweaver; fork divergence was not reconstructed.",
        "role": "TTRPG engine. Image tool is prompt-to-handout, not photo-to-mesh.",
    },
}

EXPRESSIONS = ("normal", "happy", "angry", "surprised")
FRAME_W = 200
FRAME_H = 300
SHEET_W = FRAME_W * 4
SHEET_H = FRAME_H
FACE_MIN_CONFIDENCE = 0.3
FACE_PADDING = 0.25
ALPHA_ON = 10
FALLBACK_HEAD_RATIO = 0.45
TRIM_PAD = 0.05
MESHY_API = "https://api.meshy.ai/openapi"
POLL_INTERVAL_MS = 5000
MAX_POLL_ATTEMPTS = 360
DEFAULT_POLYCOUNT = 10000
DEFAULT_HEIGHT_M = 1.7
TEXTURE_MAX = 1024


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))


def slugify(name: str) -> str:
    """game-creator scripts/build-character.mjs:50."""
    out = []
    prev_dash = False
    for ch in name.lower():
        if "a" <= ch <= "z" or "0" <= ch <= "9":
            out.append(ch)
            prev_dash = False
        else:
            if not prev_dash:
                out.append("-")
                prev_dash = True
    return "".join(out).strip("-")


def mime_from_magic(buf: bytes) -> str:
    """process-head.mjs:40-43. Unknown magic stays image/png, matching the donor default."""
    if len(buf) >= 2 and buf[0] == 0xFF and buf[1] == 0xD8:
        return "image/jpeg"
    if len(buf) >= 2 and buf[0] == 0x89 and buf[1] == 0x50:
        return "image/png"
    if len(buf) >= 2 and buf[0] == 0x52 and buf[1] == 0x49:
        return "image/webp"
    return "image/png"


def fill_expression_slots(found: dict[str, str]) -> dict:
    """Tiered fallback from skills/game-assets/character-pipeline.md:249-274.

    Donor rule: if 1–3 images exist, duplicate the preferred `normal` image
    (else the first available) into empty slots before spritesheet build.
    This function does not download anything.
    """
    present = {k: v for k, v in found.items() if v and k in EXPRESSIONS}
    if not present:
        return {"tier": 4, "slots": {}, "duplicated": list(EXPRESSIONS), "note": "no photo; pixel-art last resort in the donor skill"}
    seed_key = "normal" if "normal" in present else next(iter(present))
    seed = present[seed_key]
    slots = {}
    duplicated = []
    for expr in EXPRESSIONS:
        if expr in present:
            slots[expr] = {"source": present[expr], "duplicated": False}
        else:
            slots[expr] = {"source": seed, "duplicated": True, "duplicated_from": seed_key}
            duplicated.append(expr)
    tier = 1 if not duplicated else (3 if len(present) == 1 else 2)
    return {"tier": tier, "slots": slots, "duplicated": duplicated, "seed": seed_key}


def face_crop_rect(img_w: int, img_h: int, face: dict, padding: float = FACE_PADDING) -> dict:
    """crop-head.mjs:199-211. face box is in source pixels."""
    pad_x = round(face["width"] * padding)
    pad_y = round(face["height"] * padding)
    crop_x = max(0, face["x"] - pad_x)
    crop_y = max(0, face["y"] - pad_y)
    crop_right = min(img_w, face["x"] + face["width"] + pad_x)
    crop_bottom = min(img_h, face["y"] + face["height"] + pad_y)
    return {
        "left": crop_x,
        "top": crop_y,
        "width": crop_right - crop_x,
        "height": crop_bottom - crop_y,
        "mode": "ssd_mobilenet_v1",
        "min_confidence": FACE_MIN_CONFIDENCE,
        "padding": padding,
        "score": face.get("score"),
    }


def fallback_bbox_crop(width: int, height: int, alpha: list[int], head_ratio: float = FALLBACK_HEAD_RATIO) -> dict:
    """crop-head.mjs:113-149. alpha is row-major length width*height, 0-255."""
    if len(alpha) != width * height:
        raise ValueError("alpha length must equal width*height")
    min_x, max_x, min_y, max_y = width, 0, height, 0
    any_on = False
    for y in range(height):
        row = y * width
        for x in range(width):
            if alpha[row + x] > ALPHA_ON:
                any_on = True
                if x < min_x:
                    min_x = x
                if x > max_x:
                    max_x = x
                if y < min_y:
                    min_y = y
                if y > max_y:
                    max_y = y
    if not any_on:
        raise ValueError("no foreground pixel above alpha 10")
    figure_w = max_x - min_x
    figure_h = max_y - min_y
    center_x = min_x + figure_w / 2
    head_h = round(figure_h * head_ratio)
    head_w = round(head_h * 0.9)
    pad = round(head_w * 0.15)
    crop_x = max(0, round(center_x - head_w / 2) - pad)
    crop_y = max(0, min_y - pad)
    crop_w = min(width - crop_x, head_w + pad * 2)
    crop_h = min(height - crop_y, head_h + pad * 2)
    return {
        "left": crop_x,
        "top": crop_y,
        "width": crop_w,
        "height": crop_h,
        "mode": "alpha_bbox_fallback",
        "head_ratio": head_ratio,
        "figure": {"x": min_x, "y": min_y, "w": figure_w, "h": figure_h},
    }


def trim_and_repad(width: int, height: int, alpha: list[int], pad_frac: float = TRIM_PAD) -> dict:
    """crop-head.mjs:155-187. Returns the extract rect; does not resample."""
    if len(alpha) != width * height:
        raise ValueError("alpha length must equal width*height")
    min_x, max_x, min_y, max_y = width, 0, height, 0
    any_on = False
    for y in range(height):
        row = y * width
        for x in range(width):
            if alpha[row + x] > ALPHA_ON:
                any_on = True
                if x < min_x:
                    min_x = x
                if x > max_x:
                    max_x = x
                if y < min_y:
                    min_y = y
                if y > max_y:
                    max_y = y
    if not any_on:
        raise ValueError("trim found no foreground")
    content_w = max_x - min_x + 1
    content_h = max_y - min_y + 1
    pad_x = round(content_w * pad_frac)
    pad_y = round(content_h * pad_frac)
    final_x = max(0, min_x - pad_x)
    final_y = max(0, min_y - pad_y)
    final_w = min(width - final_x, content_w + pad_x * 2)
    final_h = min(height - final_y, content_h + pad_y * 2)
    return {
        "left": final_x,
        "top": final_y,
        "width": final_w,
        "height": final_h,
        "content": {"w": content_w, "h": content_h},
    }


def contain_fit(src_w: int, src_h: int, frame_w: int = FRAME_W, frame_h: int = FRAME_H) -> dict:
    """sharp contain into a frame. build-spritesheet.mjs:64-69. Integer floor, centered."""
    if src_w <= 0 or src_h <= 0:
        raise ValueError("source size must be positive")
    scale = min(frame_w / src_w, frame_h / src_h)
    dw = max(1, math.floor(src_w * scale))
    dh = max(1, math.floor(src_h * scale))
    # sharp contain centers the residual; we record the offset inside the frame
    return {
        "width": dw,
        "height": dh,
        "offset_x": (frame_w - dw) // 2,
        "offset_y": (frame_h - dh) // 2,
        "scale": scale,
    }


def spritesheet_plan(slots: dict) -> dict:
    frames = []
    for i, expr in enumerate(EXPRESSIONS):
        slot = slots.get(expr)
        frames.append({
            "index": i,
            "expression": expr,
            "constant": expr.upper() if expr != "surprised" else "SURPRISED",
            "left": i * FRAME_W,
            "top": 0,
            "frame_w": FRAME_W,
            "frame_h": FRAME_H,
            "source": None if not slot else slot["source"],
            "empty": slot is None,
        })
    return {"sheet_w": SHEET_W, "sheet_h": SHEET_H, "frames": frames, "order": list(EXPRESSIONS)}


def meshy_image_payload(image_ref: str, *, ai_model: str = "latest", polycount: int = DEFAULT_POLYCOUNT,
                        pbr: bool = False, topology: str = "triangle") -> dict:
    """meshy-generate.mjs imageTo3D payload, lines 428-435. Local paths become a data-URI marker, not the bytes."""
    if image_ref.startswith("http://") or image_ref.startswith("https://") or image_ref.startswith("data:"):
        image_url = image_ref if not image_ref.startswith("data:") else "(base64-omitted)"
        transport = "url" if image_ref.startswith("http") else "data-uri"
    else:
        image_url = "(local-file-as-base64-data-uri)"
        transport = "local-file"
    return {
        "endpoint": "POST /v1/image-to-3d",
        "base": MESHY_API,
        "transport": transport,
        "body": {
            "image_url": image_url,
            "ai_model": ai_model,
            "topology": topology,
            "target_polycount": polycount,
            "enable_pbr": pbr,
            "should_texture": True,
        },
        "poll": {"path": "GET /v1/image-to-3d/{id}", "interval_ms": POLL_INTERVAL_MS, "max_attempts": MAX_POLL_ATTEMPTS},
        "then": ["download model_urls.glb", f"optimize texture {TEXTURE_MAX} webp meshopt", "write .meta.json"],
    }


def meshy_text_stages(prompt: str, *, preview_only: bool = False, pbr: bool = False) -> list[dict]:
    stages = [{
        "stage": "preview",
        "endpoint": "POST /v2/text-to-3d",
        "body": {"mode": "preview", "prompt": prompt, "ai_model": "latest", "topology": "triangle",
                 "target_polycount": DEFAULT_POLYCOUNT},
    }]
    if not preview_only:
        stages.append({
            "stage": "refine",
            "endpoint": "POST /v2/text-to-3d",
            "body": {"mode": "refine", "preview_task_id": "{previewId}", "enable_pbr": pbr},
        })
    return stages


def rig_decision(kind: str) -> dict:
    """Humanoid/animal-with-legs rig; props do not. Skill text, not a mesh classifier we ran."""
    rig = kind in {"humanoid", "animal_legged"}
    return {
        "rig": rig,
        "endpoint": "POST /v1/rigging" if rig else None,
        "body": {"input_task_id": "{generateTaskId}", "height_meters": DEFAULT_HEIGHT_M} if rig else None,
        "included_clips": ["walking", "running"] if rig else [],
        "integrate": "SkeletonUtils.clone + AnimationMixer" if rig else "scene.clone(true)",
        "reason": "donor: biped/legged skeletal animation" if rig else "donor: props skip rigging",
    }


def poll_outcome(status: str) -> str:
    if status == "SUCCEEDED":
        return "success"
    if status in {"FAILED", "CANCELED"}:
        return "failure"
    if status in {"PENDING", "IN_PROGRESS"}:
        return "continue"
    return "failure"


def optimize_plan(texture_size: int = TEXTURE_MAX, compress: bool = True) -> dict:
    cmd = "npx --yes @gltf-transform/cli optimize {tmp} {out} "
    cmd += "--compress meshopt --texture-compress webp" if compress else "--texture-compress webp"
    return {
        "resize": f"npx --yes @gltf-transform/cli resize {{in}} {{tmp}} --width {texture_size} --height {texture_size}",
        "optimize": cmd,
        "on_missing_cli": "skip and keep original GLB",
        "runtime_requirement": "GLTFLoader.setMeshoptDecoder(MeshoptDecoder)",
    }


def worldlabs_plan(image_ref: str | None, prompt: str | None) -> dict:
    mode = "image" if image_ref else "text"
    return {
        "prefer": "image",
        "mode": mode,
        "endpoint_family": "https://api.worldlabs.ai/marble/v1",
        "auth_header": "WLT-Api-Key",
        "outputs": ["{slug}.spz", "{slug}-500k.spz", "{slug}-100k.spz", "{slug}-collider.glb", "{slug}-pano.jpg", "{slug}.meta.json"],
        "renderer": "@sparkjsdev/spark@^2.0.0",
        "three_pin": "^0.180.0",
        "known_fixes_from_skill": [
            "SPZ Y-flip: rotation.x = Math.PI on splat and collider; do not scale.y = -1",
            "after flip, raycast upward from y=-50",
            "do not use panorama as scene.background",
            "SparkRenderer must exist before SplatMesh",
        ],
        "input": {"image": image_ref, "prompt": prompt},
    }


def loreweaver_image_contract() -> dict:
    return {
        "tool": "ImageTools.generate_image",
        "path": "agent/kp_tools_images.py",
        "inputs": ["prompt", "kind in {scene, portrait, item}", "caption"],
        "photo_conditioned": False,
        "gates": ["imagegen configured", "allow_imagegen_request rate limit", "player-safe prompt (docstring)"],
        "side_effect": "register blob in MediaStore and publish media frame",
        "not_this_pipeline": "does not crop a face, rig a mesh, or consume a reference photo",
    }


# --- behavior tree ----------------------------------------------------------

def bt_document() -> dict:
    """Donor procedure as a behavior tree. Remote and likeness-fetch leaves are held."""
    return {
        "id": "photo_to_embodiment",
        "version": "1.0.0",
        "source": PINS["game-creator"],
        "semantics": "selector = first SUCCESS child; sequence = all children SUCCESS; a HELD leaf is not SUCCESS",
        "policy": {
            "likeness_web_fetch": "HELD",
            "reason": "Donor skill searches the web for named people's photographs. This reconstruction keeps that node in the tree and does not execute it. Operator-supplied image paths are the only photo inputs the runner accepts.",
        },
        "root": {
            "type": "selector",
            "id": "route",
            "children": [
                _seq("photo_composite_2d", "Named or photo character for a 2D Phaser game", [
                    _cond("want_2d_character", "blackboard.route == 'character_2d'"),
                    _action("library_lookup", "If assets/characters manifest already has the slug, copy sprites and stop."),
                    _action("hold_web_search", "SOURCE node: WebSearch four expression photos of a named person. HELD unless the operator already supplied files.", held=True),
                    _action("tier_select", "fill_expression_slots over operator-supplied raw/{normal,happy,angry,surprised}.*"),
                    _action("bg_remove", "For each new raw file: MIME from magic bytes; @imgly/background-removal-node model=medium output=foreground PNG."),
                    _action("face_crop", "SSD MobileNet v1 minConfidence 0.3, pad 0.25. Else alpha>10 bbox, head_ratio 0.45, then trim pad 0.05."),
                    _action("spritesheet", "800x300 PNG, frames 200x300, order normal|happy|angry|surprised, sharp fit=contain."),
                    _action("bobblehead", "Phaser Container: arms, Graphics body from unit U, head sprite on top. Never a floating head."),
                    _action("wire_expressions", "EXPRESSION 0..3, hold 600ms, EventBus PLAYER_DAMAGED→ANGRY, SCORE_CHANGED→HAPPY."),
                ]),
                _seq("image_to_3d_character", "Humanoid from a reference image", [
                    _cond("want_3d_character", "blackboard.route == 'character_3d'"),
                    _cond("have_meshy_key", "blackboard.meshy_key == true"),
                    _action("image_to_3d", "POST /v1/image-to-3d should_texture=true. Local file → base64 data URI. Poll 5s, max 360."),
                    _action("rig", "POST /v1/rigging height_meters default 1.7. Download rigged GLB plus walking and running."),
                    _action("optimize", "resize textures to 1024, gltf-transform dedup/prune/weld, meshopt, webp. Skip if CLI missing."),
                    _action("verify_integrate", "log bbox, rotationY often Math.PI, feet on -min.y, SkeletonUtils.clone, fadeToAction, mixer.update."),
                ]),
                _seq("image_to_3d_prop", "Single object, no rig", [
                    _cond("want_prop", "blackboard.route == 'prop_3d'"),
                    _cond("have_meshy_key", "blackboard.meshy_key == true"),
                    _action("image_or_text_to_3d", "Image route if a photo exists, else text preview→refine. One object per prompt."),
                    _action("skip_rig", "Props, vehicles, buildings are not rigged."),
                    _action("optimize_static", "Same GLB optimize. Integrate with scene.clone(true), not SkeletonUtils."),
                ]),
                _seq("world_from_photo", "Environment, not a character", [
                    _cond("want_world", "blackboard.route == 'world'"),
                    _cond("have_worldlabs_key", "blackboard.worldlabs_key == true"),
                    _action("image_first", "Ask for a reference image before text. POST Marble image mode."),
                    _action("download_tiers", "full, 500k, 100k SPZ + collider GLB + panorama + meta."),
                    _action("spark_integrate", "SparkRenderer before SplatMesh; three@^0.180; antialias false; Y-flip and upward raycast."),
                ]),
                _seq("pixel_from_reference", "2D sprite, not a photo composite", [
                    _cond("want_pixel", "blackboard.route == 'pixel_sprite'"),
                    _cond("have_rd_key", "blackboard.retrodiffusion_key == true"),
                    _action("img2img_or_generate", "retrodiffusion-generate.mjs. img2img strength 0.5-0.8. Paid. pixelArt:true in Phaser."),
                ]),
                _seq("not_loreweaver", "Reject the wrong donor", [
                    _cond("route_is_lore", "blackboard.route == 'lore_handout'"),
                    _action("prompt_handout_only", "Loreweaver generate_image(prompt, kind) is not photo-conditioned and does not emit a mesh."),
                ]),
                _seq("fallback_library", "No paid key", [
                    _action("tier_fallback", "3D: assets/3d-characters manifest, then Sketchfab/Poly Haven/Poly.pizza, then BoxGeometry. 2D: hand-coded matrices."),
                ]),
            ],
        },
    }


def _seq(node_id: str, title: str, children: list) -> dict:
    return {"type": "sequence", "id": node_id, "title": title, "children": children}


def _cond(node_id: str, predicate: str) -> dict:
    return {"type": "condition", "id": node_id, "predicate": predicate}


def _action(node_id: str, summary: str, held: bool = False) -> dict:
    node = {"type": "action", "id": node_id, "summary": summary}
    if held:
        node["held"] = True
    return node


class Status:
    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"
    HELD = "HELD"


def _pred(board: dict, text: str) -> bool:
    # tiny predicate language used only by this tree
    if text == "blackboard.route == 'character_2d'":
        return board.get("route") == "character_2d"
    if text == "blackboard.route == 'character_3d'":
        return board.get("route") == "character_3d"
    if text == "blackboard.route == 'prop_3d'":
        return board.get("route") == "prop_3d"
    if text == "blackboard.route == 'world'":
        return board.get("route") == "world"
    if text == "blackboard.route == 'pixel_sprite'":
        return board.get("route") == "pixel_sprite"
    if text == "blackboard.route == 'lore_handout'":
        return board.get("route") == "lore_handout"
    if text == "blackboard.meshy_key == true":
        return bool(board.get("meshy_key"))
    if text == "blackboard.worldlabs_key == true":
        return bool(board.get("worldlabs_key"))
    if text == "blackboard.retrodiffusion_key == true":
        return bool(board.get("retrodiffusion_key"))
    raise KeyError(text)


def tick(node: dict, board: dict, trace: list) -> str:
    kind = node["type"]
    if kind == "condition":
        ok = _pred(board, node["predicate"])
        status = Status.SUCCESS if ok else Status.FAILURE
        trace.append({"id": node["id"], "status": status})
        return status
    if kind == "action":
        if node.get("held"):
            trace.append({"id": node["id"], "status": Status.HELD, "effect": "not executed"})
            return Status.HELD
        effect = _effect(node["id"], board)
        status = effect.get("status", Status.SUCCESS)
        trace.append({"id": node["id"], "status": status, "effect": {k: v for k, v in effect.items() if k != "status"}})
        return status
    if kind == "sequence":
        for child in node["children"]:
            status = tick(child, board, trace)
            if status != Status.SUCCESS:
                trace.append({"id": node["id"], "status": status})
                return status
        trace.append({"id": node["id"], "status": Status.SUCCESS})
        return Status.SUCCESS
    if kind == "selector":
        last = Status.FAILURE
        for child in node["children"]:
            status = tick(child, board, trace)
            if status == Status.SUCCESS:
                trace.append({"id": node["id"], "status": Status.SUCCESS, "via": child["id"]})
                return Status.SUCCESS
            last = status
        trace.append({"id": node["id"], "status": last})
        return last
    raise KeyError(kind)


def _effect(action_id: str, board: dict) -> dict:
    photos = board.get("photos") or {}
    if action_id == "library_lookup":
        known = set(board.get("library_slugs") or [])
        slug = board.get("slug")
        if slug in known:
            board["plan"] = {"copied_from_library": slug}
            return {"status": Status.SUCCESS, "copied": slug, "short_circuit": True}
        # not in library: sequence must continue, so this is SUCCESS meaning "checked, absent"
        return {"status": Status.SUCCESS, "copied": None}
    if action_id == "tier_select":
        filled = fill_expression_slots(photos)
        board["slots"] = filled
        if filled["tier"] == 4:
            return {"status": Status.FAILURE, "tier": 4}
        return {"status": Status.SUCCESS, "tier": filled["tier"], "duplicated": filled["duplicated"]}
    if action_id == "bg_remove":
        mimes = {k: mime_from_magic(v["magic"]) for k, v in photos.items() if isinstance(v, dict) and "magic" in v}
        board["mimes"] = mimes
        return {"status": Status.SUCCESS, "model": "imgly-isnet-medium", "mimes": mimes, "executed": "local-mime-only"}
    if action_id == "face_crop":
        crops = {}
        for expr, photo in photos.items():
            if not isinstance(photo, dict):
                continue
            if photo.get("face"):
                crops[expr] = face_crop_rect(photo["w"], photo["h"], photo["face"])
            elif photo.get("alpha") is not None:
                crops[expr] = fallback_bbox_crop(photo["w"], photo["h"], photo["alpha"])
        board["crops"] = crops
        return {"status": Status.SUCCESS, "crops": crops}
    if action_id == "spritesheet":
        plan = spritesheet_plan(board.get("slots", {}).get("slots", {}))
        fits = {}
        for expr, photo in photos.items():
            if isinstance(photo, dict) and photo.get("w"):
                fits[expr] = contain_fit(photo["w"], photo["h"])
        board["spritesheet"] = plan
        board["fits"] = fits
        return {"status": Status.SUCCESS, "sheet": [plan["sheet_w"], plan["sheet_h"]], "fits": fits}
    if action_id == "bobblehead":
        width = board.get("game_width", 480)
        unit = width * 0.012
        board["body"] = {"U": unit, "head_h": width * 0.25, "frame": [FRAME_W, FRAME_H]}
        return {"status": Status.SUCCESS, "U": unit}
    if action_id == "wire_expressions":
        return {"status": Status.SUCCESS, "map": {"NORMAL": 0, "HAPPY": 1, "ANGRY": 2, "SURPRISED": 3}, "hold_ms": 600}
    if action_id == "image_to_3d":
        payload = meshy_image_payload(board["image"], pbr=bool(board.get("pbr")))
        board["meshy"] = payload
        board["rig"] = rig_decision("humanoid")
        return {"status": Status.SUCCESS, "payload": payload, "remote": "NOT_CALLED"}
    if action_id == "rig":
        return {"status": Status.SUCCESS, "rig": board.get("rig"), "remote": "NOT_CALLED"}
    if action_id == "optimize" or action_id == "optimize_static":
        plan = optimize_plan()
        board["optimize"] = plan
        return {"status": Status.SUCCESS, "plan": plan, "remote": "NOT_CALLED"}
    if action_id == "verify_integrate":
        return {"status": Status.SUCCESS, "checks": ["bbox", "facing", "floor", "SkeletonUtils", "mixer.update"]}
    if action_id == "image_or_text_to_3d":
        if board.get("image"):
            board["meshy"] = meshy_image_payload(board["image"])
        else:
            board["meshy"] = {"stages": meshy_text_stages(board.get("prompt") or "object")}
        board["rig"] = rig_decision("prop")
        return {"status": Status.SUCCESS, "remote": "NOT_CALLED", "rig": False}
    if action_id == "skip_rig":
        return {"status": Status.SUCCESS, "rig": False}
    if action_id == "image_first":
        board["world"] = worldlabs_plan(board.get("image"), board.get("prompt"))
        return {"status": Status.SUCCESS, "remote": "NOT_CALLED", "mode": board["world"]["mode"]}
    if action_id == "download_tiers":
        return {"status": Status.SUCCESS, "files": board["world"]["outputs"], "remote": "NOT_CALLED"}
    if action_id == "spark_integrate":
        return {"status": Status.SUCCESS, "fixes": board["world"]["known_fixes_from_skill"]}
    if action_id == "img2img_or_generate":
        return {"status": Status.SUCCESS, "remote": "NOT_CALLED", "paid": True,
                "strength_band": [0.5, 0.8], "phaser": {"pixelArt": True, "roundPixels": True}}
    if action_id == "tier_fallback":
        return {"status": Status.SUCCESS, "order": ["3d-characters manifest", "sketchfab", "polyhaven", "polypizza", "procedural"]}
    if action_id == "prompt_handout_only":
        board["lore"] = loreweaver_image_contract()
        return {"status": Status.SUCCESS, "photo_conditioned": False}
    raise KeyError(action_id)


def run_tree(board: dict) -> dict:
    tree = bt_document()
    trace: list = []
    # library short-circuit: if lookup copied, skip the rest of the 2d sequence.
    # Implemented by pre-check so the sequence stays faithful when the slug is new.
    status = tick(tree["root"], board, trace)
    if board.get("plan", {}).get("copied_from_library"):
        status = Status.SUCCESS
    return {"status": status, "trace": trace, "blackboard": {k: v for k, v in board.items() if k != "photos" or True}}


# --- cards ------------------------------------------------------------------

def evidence(repo: str, path: str, lines: str, note: str) -> dict:
    pin = PINS[repo]
    return {
        "repo": f"{pin['owner']}/{repo}",
        "sha": pin["sha"],
        "path": path,
        "lines": lines,
        "note": note,
    }


def cards() -> list[dict]:
    rows = [
        {
            "id": "gc-photo-composite-orchestrator",
            "status": "REPORTED",
            "title": "2D photo character is four expression stills, not a mesh",
            "claim": "build-character.mjs walks normal, happy, angry, surprised. For each raw image it runs process-head.mjs then crop-head.mjs, then build-spritesheet.mjs writes an 800×300 sheet. It does not estimate a skeleton or an SDF.",
            "evidence": [evidence("game-creator", "scripts/build-character.mjs", "1-126", "orchestrator"),
                         evidence("game-creator", "scripts/build-spritesheet.mjs", "22-26", "800x300, 200x300 frames")],
        },
        {
            "id": "gc-bg-removal",
            "status": "REPORTED",
            "title": "Background removal is ISNet via @imgly, medium model, foreground PNG",
            "claim": "process-head.mjs detects JPEG/PNG/WEBP from magic bytes, defaults unknown bytes to image/png, and calls removeBackground with model 'medium' and output type 'foreground'. First run downloads about 40 MB of model files. The skill text's '80 MB' comment disagrees with the header's '40 MB'; both are comments, not measurements we made.",
            "evidence": [evidence("game-creator", "scripts/process-head.mjs", "38-52", "magic bytes and model: medium")],
        },
        {
            "id": "gc-face-crop",
            "status": "VERIFIED",
            "title": "Face crop math matches crop-head.mjs and was re-executed locally",
            "claim": "Primary crop is @vladmandic/face-api SSD MobileNet v1, minConfidence 0.3, padding 0.25 of the face box, clamped to the image. If no face: alpha>10 bounding box, head height 45% of the figure, head width 90% of that, 15% pad. A second pass trims and re-adds 5% padding. Local tests re-ran the arithmetic, not the neural detector.",
            "evidence": [evidence("game-creator", "scripts/crop-head.mjs", "94-233", "detect, fallback, trim")],
        },
        {
            "id": "gc-expression-contract",
            "status": "REPORTED",
            "title": "Expression indices are a wire protocol",
            "claim": "NORMAL=0, HAPPY=1, ANGRY=2, SURPRISED=3. Non-normal expressions revert after 600 ms. EventBus names in the skill: PLAYER_DAMAGED→angry, SCORE_CHANGED→happy, SPECTACLE_STREAK→surprised. The bobblehead body is Phaser Graphics scaled from U = GAME.WIDTH * 0.012; the head sprite is a separate object. Floating heads are forbidden by the skill.",
            "evidence": [evidence("game-creator", "skills/game-assets/character-pipeline.md", "39-197", "constants, wiring, body")],
        },
        {
            "id": "gc-tier-fallback",
            "status": "VERIFIED",
            "title": "Missing expression photos are duplicated, not synthesized",
            "claim": "The skill's tiers: 4 distinct photos; else duplicate normal into empty slots (tier 2 or 3); else give up on the photo composite and draw a 32×48 caricature. fill_expression_slots reproduces the duplication rule and was executed in this packet. Web search for a named person's photos is in the donor skill and is HELD here.",
            "evidence": [evidence("game-creator", "skills/game-assets/character-pipeline.md", "199-286", "tiers 1-4")],
        },
        {
            "id": "gc-meshy-image-to-3d",
            "status": "REPORTED",
            "title": "Objects and 3D characters from photos go through Meshy, opaquely",
            "claim": "imageTo3D posts image_url, ai_model, topology, target_polycount, enable_pbr, should_texture=true to /v1/image-to-3d. A local path is base64'd into a data URI. The script polls every 5 seconds up to 360 times. It then downloads model_urls.glb. No marching cubes, UV unwrap, or heat-map skinning is in this repository; those steps are inside Meshy.",
            "evidence": [evidence("game-creator", "scripts/meshy-generate.mjs", "60-62", "poll bounds"),
                         evidence("game-creator", "scripts/meshy-generate.mjs", "400-468", "imageTo3D"),
                         evidence("game-creator", "skills/meshyai/api-reference.md", "61-95", "endpoints")],
        },
        {
            "id": "gc-rig-gate",
            "status": "REPORTED",
            "title": "Rigging is mandatory only for bipeds and legged animals",
            "claim": "Rig posts input_task_id and height_meters (CLI default 1.7) to /v1/rigging and expects walking and running GLBs. The skill says rigging fails on vehicles, abstract shapes, and untextured previews. Static props use scene.clone(true). Animated characters must use SkeletonUtils.clone or they T-pose.",
            "evidence": [evidence("game-creator", "skills/meshyai/rigging-pipeline.md", "5-37", "when to rig"),
                         evidence("game-creator", "skills/game-3d-assets/SKILL.md", "237-244", "clone vs SkeletonUtils")],
        },
        {
            "id": "gc-glb-optimize",
            "status": "REPORTED",
            "title": "GLB optimize is resize 1024 then meshopt and WebP, and it can no-op",
            "claim": "optimize-glb.mjs resizes with @gltf-transform/cli, then optimize --compress meshopt --texture-compress webp. If the CLI is missing or a step fails, it keeps the original file. The skill's '80–95% smaller' is a claim, not a measurement from this packet.",
            "evidence": [evidence("game-creator", "scripts/optimize-glb.mjs", "98-169", "resize then optimize")],
        },
        {
            "id": "gc-worldlabs",
            "status": "REPORTED",
            "title": "Photo-to-world is a separate Gaussian splat path",
            "claim": "World Labs Marble is preferred image-first. Outputs are SPZ tiers (full, 500k, 100k), a collider GLB, a panorama, and meta.json. Rendering is SparkJS 2 with three pinned near 0.180. The skill records a Y-axis flip of rotation.x = PI and an upward raycast after that flip. This is an environment, not a character.",
            "evidence": [evidence("game-creator", "skills/worldlabs/SKILL.md", "23-102", "image first and outputs"),
                         evidence("game-creator", "skills/worldlabs/SKILL.md", "324-334", "Y-flip and raycast")],
        },
        {
            "id": "gc-retrodiffusion",
            "status": "REPORTED",
            "title": "Pixel sprites can be image-conditioned but are not the photo-composite path",
            "claim": "retrodiffusion-generate.mjs supports img2img with a strength knob (skill: useful band 0.5–0.8), plus generate, animate, tileset, edit. It is a paid API. Phaser must set pixelArt and roundPixels. The skill explicitly says not to use it for 3D.",
            "evidence": [evidence("game-creator", "skills/retrodiffusion/SKILL.md", "105-117", "img2img"),
                         evidence("game-creator", "skills/retrodiffusion/SKILL.md", "33-34", "not for 3D")],
        },
        {
            "id": "gc-provenance-split",
            "status": "INFERENCE",
            "title": "README install target and pinned remote may not be the same repo name",
            "claim": "The pinned tree is Anil-matcha/game-creator @ 4e64b83 (2026-05-25). README install lines say `npx skills add playableintelligence/game-creator`. This packet did not diff those remotes. Treat the SHA we read as the evidence boundary.",
            "evidence": [evidence("game-creator", "README.md", "15-17", "install target name")],
        },
        {
            "id": "catalog-awesome-game",
            "status": "SOURCE_CLAIM",
            "title": "Awesome AI Game Generation names Meshy and Tripo as image-to-3D, without code",
            "claim": "The list says Meshy covers text/image-to-3D, auto-rigging, and 500+ animation presets, and Tripo3D averages about 8 seconds. Those sentences are catalog claims. They are not algorithms and were not timed here. The same file is the only place Matrix-Game and HunyuanWorld appear, as links.",
            "evidence": [evidence("awesome-ai-game-generation", "README.md", "56-64", "asset generator list")],
        },
        {
            "id": "catalog-astra",
            "status": "SOURCE_CLAIM",
            "title": "Astra note: image reference first, then a 3D scene",
            "claim": "awesome-gpt-6-astra case 23 reports a developer one-shotting a 3D game by generating reference art with an image model and then building the scene around it. It is a single reported anecdote with an X status URL, not a reproducible algorithm and not game-creator.",
            "evidence": [evidence("awesome-gpt-6-astra", "README.md", "396-398", "case 23")],
        },
        {
            "id": "catalog-saas",
            "status": "SOURCE_CLAIM",
            "title": "Vibecoded SaaS list does not contain the photo-to-character procedure",
            "claim": "The README points at Open Generative AI, Midjourney, and Photopea as image tools. No spritesheet, rig, or mesh procedure is specified. Useful only as a map of neighboring products.",
            "evidence": [evidence("awesome-vibecoded-saas", "README.md", "12-33", "image studio links")],
        },
        {
            "id": "lw-not-photo-mesh",
            "status": "REPORTED",
            "title": "Loreweaver generate_image is a gated prompt handout",
            "claim": "ImageTools.generate_image takes prompt, kind (scene|portrait|item), and caption. It rate-limits, calls an image provider, stores a blob, and publishes a media frame. The docstring forbids player-unknown information in the prompt. There is no photo input and no 3D output. Character sheets are generated by rules, not by a picture.",
            "evidence": [evidence("loreweaver", "agent/kp_tools_images.py", "31-76", "generate_image")],
        },
        {
            "id": "correction-s44",
            "status": "INFERENCE",
            "title": "Do not merge this donor with the Season 44 Matrix-3D dossier",
            "claim": "A Drive note dated 2026-10-01 describes an 8-stage SDF, marching-cubes, and VRM pipeline attributed to SkyworkAI repos. Those stages are not in the five repositories pinned here. game-creator's photo paths are (1) 2D ISNet + face crop + spritesheet + cartoon body and (2) an opaque Meshy image-to-3D HTTP job. Importing the Season 44 vertex counts into this capsule would be a false merge.",
            "evidence": [evidence("game-creator", "scripts/build-character.mjs", "1-16", "the actual 2D stages")],
        },
    ]
    for row in rows:
        blob = json.dumps({k: row[k] for k in ("id", "status", "title", "claim", "evidence")}, sort_keys=True)
        row["sha256"] = sha256_text(blob)
        row["scnug"] = _scnug(row)
    return rows


def _scnug(row: dict) -> dict:
    """Ranking metadata only. Not a calibrated probability and not a permission."""
    status = row["status"]
    grounded = {"VERIFIED": 5, "REPORTED": 4, "SOURCE_CLAIM": 2, "INFERENCE": 3}[status]
    specific = 5 if status == "VERIFIED" else 4 if status == "REPORTED" else 2
    return {
        "S": specific,
        "C": 4 if len(row["evidence"]) > 1 else 3,
        "N": 5 if row["id"] == "correction-s44" else 3,
        "U": 5 if row["id"].startswith("gc-") else 2,
        "G": grounded,
        "note": "ordinal rank for retrieval, not confidence",
    }


# --- bm25 -------------------------------------------------------------------

def _tokenize(text: str) -> list[str]:
    raw = "".join(ch.lower() if ch.isalnum() else " " for ch in text).split()
    stop = {"the", "a", "an", "of", "and", "to", "is", "in", "not", "for", "or", "this", "with"}
    return [t for t in raw if t not in stop and len(t) > 1]


def bm25_rank(query: str, docs: list[dict], k1: float = 1.2, b: float = 0.75) -> list[dict]:
    tokenized = [_tokenize(d["title"] + " " + d["claim"]) for d in docs]
    n = len(docs)
    avg = sum(len(t) for t in tokenized) / n
    df: Counter = Counter()
    for toks in tokenized:
        df.update(set(toks))
    q = _tokenize(query)
    scored = []
    for doc, toks in zip(docs, tokenized):
        tf = Counter(toks)
        score = 0.0
        for term in q:
            if term not in tf:
                continue
            idf = math.log(1 + (n - df[term] + 0.5) / (df[term] + 0.5))
            freq = tf[term]
            score += idf * (freq * (k1 + 1)) / (freq + k1 * (1 - b + b * len(toks) / avg))
        scored.append({"id": doc["id"], "score": round(score, 4)})
    scored.sort(key=lambda r: (-r["score"], r["id"]))
    return scored


# --- store, capsule, wiki ---------------------------------------------------

def build_capsule(card_rows: list[dict], tree: dict, tests: dict) -> dict:
    atoms = []
    for row in card_rows:
        atoms.append({
            "id": row["id"],
            "status": row["status"],
            "title": row["title"],
            "claim": row["claim"],
            "evidence": row["evidence"],
            "sha256": row["sha256"],
            "scnug": row["scnug"],
        })
    nodes = [{"id": a["id"], "kind": "atom"} for a in atoms]
    nodes.append({"id": "bt:photo_to_embodiment", "kind": "procedure"})
    edges = [{"from": a["id"], "to": "bt:photo_to_embodiment", "rel": "informs_procedure"} for a in atoms if a["id"].startswith("gc-")]
    edges.append({"from": "lw-not-photo-mesh", "to": "bt:photo_to_embodiment", "rel": "negative_control"})
    edges.append({"from": "correction-s44", "to": "bt:photo_to_embodiment", "rel": "boundary"})
    body = {
        "okf_c": "3.0",
        "chain_id": CHAIN,
        "chain_index": 0,
        "parent": None,
        "related_not_parent": ["eve-repo-mining-2026-10-01"],
        "created": NOW,
        "producer": "grok_eve fly dispatch — photo/object/character packet",
        "fly": {
            "harness_present_in_this_runtime": False,
            "what_ran": "BM25 over the 16 cards below. No synaptic weights, no Merkle season continuation, no regex-rule induction.",
            "likeness_policy": "web-fetch of named-person photographs is a HELD tree leaf",
            "remote_calls": 0,
        },
        "pins": PINS,
        "atoms": atoms,
        "procedure": {
            "id": "bt:photo_to_embodiment",
            "file": "bt/photo_to_embodiment.bt.json",
            "runner": "bt/photo_to_embodiment.py",
            "local_execution": tests,
        },
        "graph": {"nodes": nodes, "edges": edges, "meaning": "citation and procedure binding, not entailment"},
        "limits": [
            "Did not execute Meshy, World Labs, Retro Diffusion, imgly, or face-api.",
            "Did not download or store photographs of real people.",
            "Did not read every file in loreweaver (715 files on disk after a depth-1 clone).",
            "Catalog sentences are SOURCE_CLAIM.",
            "SCNUG numbers are ranks, not probabilities.",
        ],
    }
    encoded = json.dumps(body, sort_keys=True, ensure_ascii=False).encode("utf-8")
    body["content_sha256"] = sha256_bytes(encoded)
    return body


def wiki(card_rows: list[dict], tests: dict, capsule_hash: str) -> str:
    lines = [
        "# Photo → object / character — reverse engineering packet",
        "",
        f"Chain `{CHAIN}` index 0. No parent. Capsule `{capsule_hash}`.",
        "Written 2026-10-01. Fly harness binaries were not in this runtime; retrieval is BM25. Remote generators were not called.",
        "",
        "## What the tool actually does",
        "",
        "game-creator does not reconstruct a photo into a rigged mesh itself. It has two photo procedures and they must not be collapsed:",
        "",
        "1. **2D person sprite.** Four stills → ISNet background removal → SSD MobileNet face crop (alpha-bbox fallback) → 800×300 spritesheet → Phaser cartoon body under the head → expression frames driven by EventBus.",
        "2. **3D object or character.** The photo is posted to Meshy `POST /v1/image-to-3d`. Meshy returns a GLB. Humanoids are then rigged by Meshy. This repo only polls, downloads, and optionally runs gltf-transform.",
        "3. **3D place.** A reference photo is preferred input to World Labs Marble, which returns Gaussian splats plus a collider, rendered by SparkJS. Not a character.",
        "",
        "Loreweaver's `generate_image` is a prompt handout (scene, portrait, or item). It is a negative control: no reference photo, no mesh.",
        "",
        "The two awesome lists and the Astra list are catalogs. Astra case 23 is an anecdote: make a reference image, then ask the model to build a 3D scene around it. That is a prompting pattern, not code.",
        "",
        "## Behavior tree",
        "",
        "File `bt/photo_to_embodiment.bt.json`. Runner `bt/photo_to_embodiment.py` (this packet's `assemble.py` is the same program).",
        "Selector order: 2D photo composite, 3D character, 3D prop, world, pixel img2img, unpaid library fallback, loreweaver rejection.",
        "The donor's web-search-for-a-face step is in the tree and **HELD**. Operator-supplied files are the only photos the runner accepts.",
        "Local geometry (slot fill, crop rectangles, spritesheet layout, MIME, payload shapes) executed. HTTP did not.",
        "",
        "## Local execution",
        "",
        "```",
        json.dumps(tests, indent=2),
        "```",
        "",
        "## Cards",
        "",
    ]
    for row in card_rows:
        ev = "; ".join(f"{e['path']}:{e['lines']}" for e in row["evidence"])
        lines.append(f"- **{row['status']}** `{row['id']}` — {row['title']}. {ev}.")
    lines += [
        "",
        "## Rebuild notes (algorithm, not a service clone)",
        "",
        "- Expression order is load-bearing: index 0 normal, 1 happy, 2 angry, 3 surprised.",
        "- Face padding and the alpha fallback constants are in `crop-head.mjs`. Re-running face-api itself needs the model files and `canvas`; this packet re-ran only the geometry.",
        "- Do not invent marching cubes, VRM blendshapes, or a 24-bone humanoid from this donor. Those are not here.",
        "- GLB runtime must set `MeshoptDecoder` or optimized files will not parse.",
        "- Animated clones must go through `SkeletonUtils.clone`.",
        "- World Labs SPZ often needs `rotation.x = Math.PI`. Negative parent scale breaks Spark.",
        "",
        "## Pins",
        "",
    ]
    for name, pin in PINS.items():
        lines.append(f"- `{pin['owner']}/{name}` `{pin['sha'][:12]}` — {pin['role']} {pin['license_note']}")
    lines.append("")
    return "\n".join(lines)


def init_db(path: Path, card_rows: list[dict], capsule_hash: str) -> None:
    if path.exists():
        path.unlink()
    con = sqlite3.connect(path)
    con.execute("PRAGMA foreign_keys = ON")
    con.executescript("""
        CREATE TABLE pins (
          repo TEXT PRIMARY KEY,
          owner TEXT NOT NULL,
          sha TEXT NOT NULL,
          committed TEXT NOT NULL,
          license_note TEXT NOT NULL
        );
        CREATE TABLE cards (
          id TEXT PRIMARY KEY,
          status TEXT NOT NULL CHECK (status IN ('VERIFIED','REPORTED','SOURCE_CLAIM','INFERENCE')),
          title TEXT NOT NULL,
          claim TEXT NOT NULL,
          sha256 TEXT NOT NULL,
          scnug_json TEXT NOT NULL
        );
        CREATE TABLE evidence (
          id INTEGER PRIMARY KEY,
          card_id TEXT NOT NULL REFERENCES cards(id),
          repo TEXT NOT NULL,
          sha TEXT NOT NULL,
          path TEXT NOT NULL,
          lines TEXT NOT NULL,
          note TEXT NOT NULL
        );
        CREATE TABLE capsule (
          chain_id TEXT PRIMARY KEY,
          chain_index INTEGER NOT NULL,
          content_sha256 TEXT NOT NULL,
          parent TEXT
        );
        CREATE VIRTUAL TABLE cards_fts USING fts5(id, title, claim, content='cards', content_rowid='rowid');
    """)
    for name, pin in PINS.items():
        con.execute(
            "INSERT INTO pins VALUES (?,?,?,?,?)",
            (name, pin["owner"], pin["sha"], pin["committed"], pin["license_note"]),
        )
    for row in card_rows:
        con.execute(
            "INSERT INTO cards VALUES (?,?,?,?,?,?)",
            (row["id"], row["status"], row["title"], row["claim"], row["sha256"], json.dumps(row["scnug"])),
        )
        for ev in row["evidence"]:
            con.execute(
                "INSERT INTO evidence (card_id, repo, sha, path, lines, note) VALUES (?,?,?,?,?,?)",
                (row["id"], ev["repo"], ev["sha"], ev["path"], ev["lines"], ev["note"]),
            )
    con.execute("INSERT INTO capsule VALUES (?,?,?,NULL)", (CHAIN, 0, capsule_hash))
    con.execute("INSERT INTO cards_fts(cards_fts) VALUES('rebuild')")
    con.commit()
    # integrity
    fk = con.execute("PRAGMA foreign_key_check").fetchall()
    if fk:
        raise SystemExit(f"foreign key check failed: {fk}")
    fts = con.execute("SELECT id FROM cards_fts WHERE cards_fts MATCH 'spritesheet'").fetchall()
    if not any(r[0] == "gc-photo-composite-orchestrator" for r in fts):
        raise SystemExit(f"fts miss: {fts}")
    con.close()


def run_tests() -> dict:
    results = []

    def check(name: str, cond: bool, detail: str = "") -> None:
        results.append({"name": name, "pass": bool(cond), "detail": detail})
        if not cond:
            raise AssertionError(f"{name}: {detail}")

    check("slug", slugify("Donald Trump") == "donald-trump", slugify("Donald Trump"))
    check("mime-jpeg", mime_from_magic(b"\xff\xd8\xff") == "image/jpeg")
    check("mime-png", mime_from_magic(b"\x89PNG") == "image/png")
    check("mime-webp", mime_from_magic(b"RIFF") == "image/webp")
    check("mime-default", mime_from_magic(b"????") == "image/png")

    one = fill_expression_slots({"normal": "n.jpg"})
    check("tier3", one["tier"] == 3 and one["slots"]["angry"]["duplicated"] and one["slots"]["angry"]["duplicated_from"] == "normal")
    two = fill_expression_slots({"normal": "n.jpg", "happy": "h.jpg"})
    check("tier2", two["tier"] == 2 and two["slots"]["happy"]["duplicated"] is False and "angry" in two["duplicated"])
    four = fill_expression_slots({k: f"{k}.jpg" for k in EXPRESSIONS})
    check("tier1", four["tier"] == 1 and four["duplicated"] == [])
    check("tier4", fill_expression_slots({})["tier"] == 4)

    # face box 100,80 size 80x80 inside 400x400, pad 0.25 → pad 20 → crop origin 80,60 size 120x120
    rect = face_crop_rect(400, 400, {"x": 100, "y": 80, "width": 80, "height": 80, "score": 0.9})
    check("face-rect", rect["left"] == 80 and rect["top"] == 60 and rect["width"] == 120 and rect["height"] == 120, str(rect))
    # clamp: face at origin
    clamped = face_crop_rect(50, 50, {"x": 0, "y": 0, "width": 40, "height": 40, "score": 0.5})
    check("face-clamp", clamped["left"] == 0 and clamped["top"] == 0 and clamped["width"] == 50 and clamped["height"] == 50, str(clamped))

    # 10x20 image, opaque column x=2..5, y=4..15 (alpha 255)
    w, h = 10, 20
    alpha = [0] * (w * h)
    for y in range(4, 16):
        for x in range(2, 6):
            alpha[y * w + x] = 255
    fb = fallback_bbox_crop(w, h, alpha)
    check("fallback-mode", fb["mode"] == "alpha_bbox_fallback")
    check("fallback-inside", 0 <= fb["left"] and fb["left"] + fb["width"] <= w and fb["height"] > 0, str(fb))

    trim_alpha = [0] * 25
    trim_alpha[6] = 255  # x=1,y=1 in 5x5
    trim_alpha[12] = 255  # x=2,y=2
    tr = trim_and_repad(5, 5, trim_alpha)
    check("trim", tr["content"]["w"] == 2 and tr["content"]["h"] == 2, str(tr))

    fit = contain_fit(400, 300)
    check("contain", fit["width"] == 200 and fit["height"] == 150 and fit["offset_y"] == 75, str(fit))

    sheet = spritesheet_plan(four["slots"])
    check("sheet", sheet["sheet_w"] == 800 and sheet["frames"][3]["left"] == 600 and sheet["frames"][0]["expression"] == "normal")

    payload = meshy_image_payload("/tmp/ref.png", pbr=True)
    check("meshy-payload", payload["body"]["should_texture"] is True and payload["body"]["enable_pbr"] is True
          and payload["transport"] == "local-file" and payload["poll"]["max_attempts"] == 360)
    check("poll", poll_outcome("SUCCEEDED") == "success" and poll_outcome("IN_PROGRESS") == "continue" and poll_outcome("FAILED") == "failure")
    check("rig-human", rig_decision("humanoid")["rig"] is True and rig_decision("prop")["rig"] is False)
    check("text-stages", len(meshy_text_stages("barrel")) == 2 and len(meshy_text_stages("barrel", preview_only=True)) == 1)

    # tree: operator 2d photos, no library hit, web search held but sequence still completes because held is... 
    # WAIT: sequence treats HELD as not SUCCESS, so the 2d sequence FAILS if hold_web_search is inside it.
    # That would make the whole selector fall through. The hold node should not fail the reconstruction
    # when photos were already supplied. Fix: the runner's hold action returns HELD only when photos are absent.
    # I'll adjust by testing after the code change... I already wrote tick() to always HELD.
    # I need to change hold behavior: if photos exist, the held node is skipped as SUCCESS with effect "not needed".
    # If photos are absent, HELD fails the 2d branch (correct: we will not web-search).
    # I'll patch _effect... hold is handled before _effect in tick(). I should change tick.

    return {"checks": results, "count": len(results), "failed": 0}


def tick(node: dict, board: dict, trace: list) -> str:  # noqa: F811 — replaced below if I forget
    return _tick_impl(node, board, trace)


def _tick_impl(node: dict, board: dict, trace: list) -> str:
    kind = node["type"]
    if kind == "condition":
        ok = _pred(board, node["predicate"])
        status = Status.SUCCESS if ok else Status.FAILURE
        trace.append({"id": node["id"], "status": status})
        return status
    if kind == "action":
        if node.get("held"):
            if board.get("photos"):
                trace.append({"id": node["id"], "status": Status.SUCCESS, "effect": "skipped; operator photos present"})
                return Status.SUCCESS
            trace.append({"id": node["id"], "status": Status.HELD, "effect": "web search for a likeness was not run"})
            return Status.HELD
        effect = _effect(node["id"], board)
        status = effect.get("status", Status.SUCCESS)
        trace.append({"id": node["id"], "status": status, "effect": {k: v for k, v in effect.items() if k != "status"}})
        return status
    if kind == "sequence":
        for child in node["children"]:
            status = _tick_impl(child, board, trace)
            if status != Status.SUCCESS:
                trace.append({"id": node["id"], "status": status})
                return status
        trace.append({"id": node["id"], "status": Status.SUCCESS})
        return Status.SUCCESS
    if kind == "selector":
        last = Status.FAILURE
        for child in node["children"]:
            status = _tick_impl(child, board, trace)
            if status == Status.SUCCESS:
                trace.append({"id": node["id"], "status": Status.SUCCESS, "via": child["id"]})
                return Status.SUCCESS
            last = status
        trace.append({"id": node["id"], "status": last})
        return last
    raise KeyError(kind)


def scenario_tests() -> dict:
    scenarios = []

    def run(name: str, board: dict, expect: str, via: str | None = None) -> None:
        # fresh board copy at top level only; nested dicts are mutated on purpose
        out = run_tree(dict(board))
        ok = out["status"] == expect
        got_via = None
        for event in out["trace"]:
            if event["id"] == "route" and "via" in event:
                got_via = event["via"]
        if via is not None and got_via != via:
            ok = False
        scenarios.append({"name": name, "pass": ok, "status": out["status"], "via": got_via, "expect": expect})
        if not ok:
            raise AssertionError(f"{name}: status={out['status']} via={got_via} trace={out['trace'][-6:]}")

    photos = {
        "normal": {"path": "raw/normal.jpg", "w": 400, "h": 300, "magic": b"\xff\xd8\xff", "face": {"x": 100, "y": 80, "width": 80, "height": 80, "score": 0.91}},
        "happy": {"path": "raw/happy.jpg", "w": 200, "h": 400, "magic": b"\x89P", "face": {"x": 40, "y": 30, "width": 90, "height": 100, "score": 0.8}},
    }
    # fill_expression_slots expects string paths, but tree's tier_select uses photos values.
    # Our fill looks at truthy values. Dicts are truthy. duplicated_from works.
    # MIME step expects dict with magic. Good.
    # BUT fill_expression_slots stores the dict as source. That's ok for the test.
    run("2d-operator-photos", {
        "route": "character_2d",
        "slug": "sample",
        "library_slugs": [],
        "photos": photos,
        "game_width": 480,
    }, Status.SUCCESS, "photo_composite_2d")

    run("2d-no-photo-held", {
        "route": "character_2d",
        "slug": "nobody",
        "library_slugs": [],
        "photos": {},
    }, Status.SUCCESS, "fallback_library")

    run("3d-character-plan", {
        "route": "character_3d",
        "meshy_key": True,
        "image": "/tmp/ref.png",
        "pbr": True,
    }, Status.SUCCESS, "image_to_3d_character")

    run("3d-no-key-fallback", {
        "route": "character_3d",
        "meshy_key": False,
        "image": "/tmp/ref.png",
    }, Status.SUCCESS, "fallback_library")

    run("prop", {
        "route": "prop_3d",
        "meshy_key": True,
        "prompt": "a wooden barrel",
    }, Status.SUCCESS, "image_to_3d_prop")

    run("world", {
        "route": "world",
        "worldlabs_key": True,
        "image": "/tmp/room.jpg",
    }, Status.SUCCESS, "world_from_photo")

    run("lore-negative", {
        "route": "lore_handout",
    }, Status.SUCCESS, "not_loreweaver")

    held = run_tree({
        "route": "character_2d",
        "slug": "nobody",
        "library_slugs": [],
        "photos": {},
    })
    held_ids = [e["id"] for e in held["trace"] if e["status"] == Status.HELD]
    ok_held = "hold_web_search" in held_ids and "photo_composite_2d" in held_ids
    scenarios.append({"name": "held-leaf-visible", "pass": ok_held, "status": held["status"], "via": held_ids, "expect": ["hold_web_search"]})
    if not ok_held:
        raise AssertionError(f"held leaf not visible: {held['trace']}")

    failed = [s for s in scenarios if not s["pass"]]
    return {"scenarios": scenarios, "count": len(scenarios), "failed": len(failed)}


def main() -> None:
    unit = run_tests()
    scen = scenario_tests()
    # confirm a 2d run actually computed a crop
    demo = run_tree({
        "route": "character_2d",
        "slug": "sample",
        "library_slugs": [],
        "game_width": 480,
        "photos": {
            "normal": {"path": "raw/normal.jpg", "w": 400, "h": 300, "magic": b"\xff\xd8\xff",
                       "face": {"x": 100, "y": 80, "width": 80, "height": 80, "score": 0.91}},
        },
    })
    crop = demo["blackboard"].get("crops", {}).get("normal")
    if not crop or crop["left"] != 80:
        raise SystemExit(f"demo crop missing: {crop}")
    if demo["blackboard"].get("spritesheet", {}).get("sheet_w") != 800:
        raise SystemExit("spritesheet not planned")
    if abs(demo["blackboard"]["body"]["U"] - 480 * 0.012) > 1e-9:
        raise SystemExit("body unit wrong")

    tests = {"unit": unit, "scenarios": scen, "demo_crop": crop, "demo_status": demo["status"]}
    card_rows = cards()
    ranking = bm25_rank("photo character spritesheet face crop", card_rows)
    if ranking[0]["id"] not in {"gc-photo-composite-orchestrator", "gc-face-crop", "gc-expression-contract", "gc-tier-fallback"}:
        raise SystemExit(f"bm25 top unexpected: {ranking[:3]}")
    tests["bm25_top"] = ranking[:5]

    tree = bt_document()
    capsule = build_capsule(card_rows, tree, tests)
    # content hash was computed before insertion; recompute stored file hash separately after write
    wiki_text = wiki(card_rows, tests, capsule["content_sha256"])

    (ROOT / "wiki").mkdir(exist_ok=True)
    (ROOT / "bt").mkdir(exist_ok=True)
    (ROOT / "okf").mkdir(exist_ok=True)
    (ROOT / "store").mkdir(exist_ok=True)
    (ROOT / "wiki" / "photo_to_object_character.md").write_text(wiki_text, encoding="utf-8")
    (ROOT / "bt" / "photo_to_embodiment.bt.json").write_text(json.dumps(tree, indent=2), encoding="utf-8")
    # runner is this file; also drop a thin alias note
    (ROOT / "bt" / "README.md").write_text(
        "Run `python3 ../assemble.py` from any cwd. The behavior-tree runner, local geometry, and tests live in assemble.py "
        "so the procedure is one file. `photo_to_embodiment.bt.json` is the declarative tree.\n",
        encoding="utf-8",
    )
    cap_path = ROOT / "okf" / "eve_photo_object_character_2026_10_01.okf-c.json"
    cap_path.write_text(json.dumps(capsule, indent=2, ensure_ascii=False), encoding="utf-8")
    file_hash = sha256_bytes(cap_path.read_bytes())
    (ROOT / "store" / "cards.jsonl").write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in card_rows) + "\n",
        encoding="utf-8",
    )
    (ROOT / "store" / "bm25.json").write_text(json.dumps(ranking, indent=2), encoding="utf-8")
    init_db(ROOT / "store" / "knowledge_store.sqlite3", card_rows, capsule["content_sha256"])
    manifest = {
        "chain_id": CHAIN,
        "capsule_content_sha256": capsule["content_sha256"],
        "capsule_file_sha256": file_hash,
        "tests": tests,
        "files": sorted(str(p.relative_to(ROOT)) for p in ROOT.rglob("*") if p.is_file() and p.name != "manifest.json"),
    }
    (ROOT / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps({
        "ok": True,
        "unit": unit["count"],
        "scenarios": scen["count"],
        "cards": len(card_rows),
        "bm25_top": ranking[0],
        "capsule_content_sha256": capsule["content_sha256"],
        "demo_via": [e for e in demo["trace"] if e["id"] == "route"][-1],
    }, indent=2))


if __name__ == "__main__":
    main()
