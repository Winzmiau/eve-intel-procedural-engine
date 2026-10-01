# Photo → object / character — reverse engineering packet

Chain `eve-photo-object-character-2026-10-01` index 0. No parent. Capsule `d9ce9afa540ca8c71d3cc84025358f2fdf76afdf6c25c22913e199ce321f93ea`.
Written 2026-10-01. Fly harness binaries were not in this runtime; retrieval is BM25. Remote generators were not called.

## What the tool actually does

game-creator does not reconstruct a photo into a rigged mesh itself. It has two photo procedures and they must not be collapsed:

1. **2D person sprite.** Four stills → ISNet background removal → SSD MobileNet face crop (alpha-bbox fallback) → 800×300 spritesheet → Phaser cartoon body under the head → expression frames driven by EventBus.
2. **3D object or character.** The photo is posted to Meshy `POST /v1/image-to-3d`. Meshy returns a GLB. Humanoids are then rigged by Meshy. This repo only polls, downloads, and optionally runs gltf-transform.
3. **3D place.** A reference photo is preferred input to World Labs Marble, which returns Gaussian splats plus a collider, rendered by SparkJS. Not a character.

Loreweaver's `generate_image` is a prompt handout (scene, portrait, or item). It is a negative control: no reference photo, no mesh.

The two awesome lists and the Astra list are catalogs. Astra case 23 is an anecdote: make a reference image, then ask the model to build a 3D scene around it. That is a prompting pattern, not code.

## Behavior tree

File `bt/photo_to_embodiment.bt.json`. Runner `bt/photo_to_embodiment.py` (this packet's `assemble.py` is the same program).
Selector order: 2D photo composite, 3D character, 3D prop, world, pixel img2img, unpaid library fallback, loreweaver rejection.
The donor's web-search-for-a-face step is in the tree and **HELD**. Operator-supplied files are the only photos the runner accepts.
Local geometry (slot fill, crop rectangles, spritesheet layout, MIME, payload shapes) executed. HTTP did not.

## Local execution

```
{
  "unit": {
    "checks": [
      {
        "name": "slug",
        "pass": true,
        "detail": "donald-trump"
      },
      {
        "name": "mime-jpeg",
        "pass": true,
        "detail": ""
      },
      {
        "name": "mime-png",
        "pass": true,
        "detail": ""
      },
      {
        "name": "mime-webp",
        "pass": true,
        "detail": ""
      },
      {
        "name": "mime-default",
        "pass": true,
        "detail": ""
      },
      {
        "name": "tier3",
        "pass": true,
        "detail": ""
      },
      {
        "name": "tier2",
        "pass": true,
        "detail": ""
      },
      {
        "name": "tier1",
        "pass": true,
        "detail": ""
      },
      {
        "name": "tier4",
        "pass": true,
        "detail": ""
      },
      {
        "name": "face-rect",
        "pass": true,
        "detail": "{'left': 80, 'top': 60, 'width': 120, 'height': 120, 'mode': 'ssd_mobilenet_v1', 'min_confidence': 0.3, 'padding': 0.25, 'score': 0.9}"
      },
      {
        "name": "face-clamp",
        "pass": true,
        "detail": "{'left': 0, 'top': 0, 'width': 50, 'height': 50, 'mode': 'ssd_mobilenet_v1', 'min_confidence': 0.3, 'padding': 0.25, 'score': 0.5}"
      },
      {
        "name": "fallback-mode",
        "pass": true,
        "detail": ""
      },
      {
        "name": "fallback-inside",
        "pass": true,
        "detail": "{'left': 1, 'top': 3, 'width': 6, 'height': 7, 'mode': 'alpha_bbox_fallback', 'head_ratio': 0.45, 'figure': {'x': 2, 'y': 4, 'w': 3, 'h': 11}}"
      },
      {
        "name": "trim",
        "pass": true,
        "detail": "{'left': 1, 'top': 1, 'width': 2, 'height': 2, 'content': {'w': 2, 'h': 2}}"
      },
      {
        "name": "contain",
        "pass": true,
        "detail": "{'width': 200, 'height': 150, 'offset_x': 0, 'offset_y': 75, 'scale': 0.5}"
      },
      {
        "name": "sheet",
        "pass": true,
        "detail": ""
      },
      {
        "name": "meshy-payload",
        "pass": true,
        "detail": ""
      },
      {
        "name": "poll",
        "pass": true,
        "detail": ""
      },
      {
        "name": "rig-human",
        "pass": true,
        "detail": ""
      },
      {
        "name": "text-stages",
        "pass": true,
        "detail": ""
      }
    ],
    "count": 20,
    "failed": 0
  },
  "scenarios": {
    "scenarios": [
      {
        "name": "2d-operator-photos",
        "pass": true,
        "status": "SUCCESS",
        "via": "photo_composite_2d",
        "expect": "SUCCESS"
      },
      {
        "name": "2d-no-photo-held",
        "pass": true,
        "status": "SUCCESS",
        "via": "fallback_library",
        "expect": "SUCCESS"
      },
      {
        "name": "3d-character-plan",
        "pass": true,
        "status": "SUCCESS",
        "via": "image_to_3d_character",
        "expect": "SUCCESS"
      },
      {
        "name": "3d-no-key-fallback",
        "pass": true,
        "status": "SUCCESS",
        "via": "fallback_library",
        "expect": "SUCCESS"
      },
      {
        "name": "prop",
        "pass": true,
        "status": "SUCCESS",
        "via": "image_to_3d_prop",
        "expect": "SUCCESS"
      },
      {
        "name": "world",
        "pass": true,
        "status": "SUCCESS",
        "via": "world_from_photo",
        "expect": "SUCCESS"
      },
      {
        "name": "lore-negative",
        "pass": true,
        "status": "SUCCESS",
        "via": "not_loreweaver",
        "expect": "SUCCESS"
      },
      {
        "name": "held-leaf-visible",
        "pass": true,
        "status": "SUCCESS",
        "via": [
          "hold_web_search",
          "photo_composite_2d"
        ],
        "expect": [
          "hold_web_search"
        ]
      }
    ],
    "count": 8,
    "failed": 0
  },
  "demo_crop": {
    "left": 80,
    "top": 60,
    "width": 120,
    "height": 120,
    "mode": "ssd_mobilenet_v1",
    "min_confidence": 0.3,
    "padding": 0.25,
    "score": 0.91
  },
  "demo_status": "SUCCESS",
  "bm25_top": [
    {
      "id": "gc-photo-composite-orchestrator",
      "score": 6.1146
    },
    {
      "id": "gc-face-crop",
      "score": 5.5077
    },
    {
      "id": "correction-s44",
      "score": 5.2602
    },
    {
      "id": "catalog-saas",
      "score": 4.311
    },
    {
      "id": "gc-worldlabs",
      "score": 2.2122
    }
  ]
}
```

## Cards

- **REPORTED** `gc-photo-composite-orchestrator` — 2D photo character is four expression stills, not a mesh. scripts/build-character.mjs:1-126; scripts/build-spritesheet.mjs:22-26.
- **REPORTED** `gc-bg-removal` — Background removal is ISNet via @imgly, medium model, foreground PNG. scripts/process-head.mjs:38-52.
- **VERIFIED** `gc-face-crop` — Face crop math matches crop-head.mjs and was re-executed locally. scripts/crop-head.mjs:94-233.
- **REPORTED** `gc-expression-contract` — Expression indices are a wire protocol. skills/game-assets/character-pipeline.md:39-197.
- **VERIFIED** `gc-tier-fallback` — Missing expression photos are duplicated, not synthesized. skills/game-assets/character-pipeline.md:199-286.
- **REPORTED** `gc-meshy-image-to-3d` — Objects and 3D characters from photos go through Meshy, opaquely. scripts/meshy-generate.mjs:60-62; scripts/meshy-generate.mjs:400-468; skills/meshyai/api-reference.md:61-95.
- **REPORTED** `gc-rig-gate` — Rigging is mandatory only for bipeds and legged animals. skills/meshyai/rigging-pipeline.md:5-37; skills/game-3d-assets/SKILL.md:237-244.
- **REPORTED** `gc-glb-optimize` — GLB optimize is resize 1024 then meshopt and WebP, and it can no-op. scripts/optimize-glb.mjs:98-169.
- **REPORTED** `gc-worldlabs` — Photo-to-world is a separate Gaussian splat path. skills/worldlabs/SKILL.md:23-102; skills/worldlabs/SKILL.md:324-334.
- **REPORTED** `gc-retrodiffusion` — Pixel sprites can be image-conditioned but are not the photo-composite path. skills/retrodiffusion/SKILL.md:105-117; skills/retrodiffusion/SKILL.md:33-34.
- **INFERENCE** `gc-provenance-split` — README install target and pinned remote may not be the same repo name. README.md:15-17.
- **SOURCE_CLAIM** `catalog-awesome-game` — Awesome AI Game Generation names Meshy and Tripo as image-to-3D, without code. README.md:56-64.
- **SOURCE_CLAIM** `catalog-astra` — Astra note: image reference first, then a 3D scene. README.md:396-398.
- **SOURCE_CLAIM** `catalog-saas` — Vibecoded SaaS list does not contain the photo-to-character procedure. README.md:12-33.
- **REPORTED** `lw-not-photo-mesh` — Loreweaver generate_image is a gated prompt handout. agent/kp_tools_images.py:31-76.
- **INFERENCE** `correction-s44` — Do not merge this donor with the Season 44 Matrix-3D dossier. scripts/build-character.mjs:1-16.

## Rebuild notes (algorithm, not a service clone)

- Expression order is load-bearing: index 0 normal, 1 happy, 2 angry, 3 surprised.
- Face padding and the alpha fallback constants are in `crop-head.mjs`. Re-running face-api itself needs the model files and `canvas`; this packet re-ran only the geometry.
- Do not invent marching cubes, VRM blendshapes, or a 24-bone humanoid from this donor. Those are not here.
- GLB runtime must set `MeshoptDecoder` or optimized files will not parse.
- Animated clones must go through `SkeletonUtils.clone`.
- World Labs SPZ often needs `rotation.x = Math.PI`. Negative parent scale breaks Spark.

## Pins

- `Anil-matcha/game-creator` `4e64b83b5fe4` — executable donor for photo-composite characters and image/text-to-3D objects README declares MIT. A raw LICENSE fetch at this SHA returned HTTP 404; do not treat the badge as a copied license file.
- `Anil-matcha/awesome-ai-game-generation` `10fac24a9cf2` — catalog. Not an implementation of photo-to-character. CC0 1.0 Universal (LICENSE file present).
- `Anil-matcha/awesome-gpt-6-astra` `5f6ccbaf684f` — catalog of reported Astra workflows, including image-then-3D. MIT (LICENSE file present). Entries are anecdotal SOURCE_CLAIMs.
- `Anil-matcha/awesome-vibecoded-saas` `a619af1f0ca9` — catalog. Points at image studios, not a photo-to-mesh algorithm. MIT (LICENSE file present).
- `Anil-matcha/loreweaver` `f61aa09a416d` — TTRPG engine. Image tool is prompt-to-handout, not photo-to-mesh. MIT (LICENSE file present). README badges and install docs point at 1A7432/loreweaver; fork divergence was not reconstructed.
