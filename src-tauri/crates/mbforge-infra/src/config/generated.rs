// ============================================================
// YAML-derived constants — included from build script output.
//
// The build script (`build.rs`) writes `OUT_DIR/constants.rs` from
// `constants.yaml` via `scripts/generate_constants.py`. This file just
// pulls it in. Do not edit; edit `constants.yaml` instead.
//
// Inner attributes apply to the included items; the generated file
// itself contains no `#![...]` attributes.
// ============================================================

#![allow(dead_code, non_snake_case)]

include!(concat!(env!("OUT_DIR"), "/constants.rs"));
