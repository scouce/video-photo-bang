---
layout: default
title: MOV Shot Technical MVP
---

# MOV Shot Technical MVP

Deterministic classical-DSP shot selection for local `.mov`, `.mp4`, `.m4v` and `.avi` files.

The CLI samples frames, detects shot boundaries, measures technical metrics, scores eight
dimensions, applies hard gates and a quality floor, and selects a Top-N that penalizes
near-duplicates. Every number is traceable to a raw measurement and a declared range.

A Streamlit client reads the run artifacts and re-ranks live, so changing a preference
weight never re-decodes the video. The app runs locally (or on Streamlit Community Cloud at
<https://video-photo-bang-pdzq4ahkdbe3eqjwm6dars.streamlit.app/>);
GitHub Pages hosts this documentation only.

See the full documentation in the repository: <https://github.com/>.
