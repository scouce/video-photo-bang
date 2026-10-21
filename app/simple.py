"""Simplified result view: galleries, previews and downloads for non-technical users.

This module only reads what the run already produced (``ui.json`` records and the exported
images). It never opens the video and never changes the scoring path: every control writes
the same config fields the technical mode shows.
"""

from __future__ import annotations

import io
import json
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

import copy_es
import cv2
import streamlit as st

PAGE_SIZE = 12
PREVIEW_EDGE = 720


@st.cache_data(show_spinner=False, max_entries=64)
def preview_bytes(path: str, mtime: float, max_edge: int = PREVIEW_EDGE) -> bytes:
    """Downscaled JPEG preview of an artifact image (full PNG stays for download)."""
    del mtime
    image = cv2.imread(path, cv2.IMREAD_COLOR)
    if image is None:
        return b""
    height, width = image.shape[:2]
    scale = min(1.0, max_edge / max(height, width))
    if scale < 1.0:
        image = cv2.resize(
            image,
            (max(1, int(round(width * scale))), max(1, int(round(height * scale)))),
            interpolation=cv2.INTER_AREA,
        )
    ok, buffer = cv2.imencode(".jpg", image, [int(cv2.IMWRITE_JPEG_QUALITY), 82])
    return buffer.tobytes() if ok else b""


@st.cache_data(show_spinner=False, max_entries=256)
def thumb_bytes(path: str, mtime: float) -> bytes:
    """Raw JPEG thumbnail, already small enough for the gallery grid."""
    del mtime
    return Path(path).read_bytes()


@st.cache_data(show_spinner=False, max_entries=4)
def file_bytes(path: str, mtime: float) -> bytes:
    del mtime
    return Path(path).read_bytes()


@st.cache_data(show_spinner="Preparando el ZIP…", max_entries=4)
def zip_bytes(paths: tuple[str, ...], names: tuple[str, ...]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_STORED) as archive:
        for path, name in zip(paths, names, strict=True):
            archive.write(path, arcname=name)
    return buffer.getvalue()


def image_path_of(shot: dict[str, Any]) -> str | None:
    """Full-resolution PNG, only written for the shots the user can take away."""
    path = shot.get("selected_frame_image_path")
    if path and Path(path).exists():
        return path
    return None


def preview_of(shot: dict[str, Any]) -> bytes:
    """Prefer the run's small JPEG; fall back to downscaling the full PNG in memory."""
    thumb = shot.get("thumb_path")
    if thumb and Path(thumb).exists():
        return thumb_bytes(thumb, Path(thumb).stat().st_mtime)
    full = image_path_of(shot)
    if full:
        return preview_bytes(full, Path(full).stat().st_mtime)
    return b""


def _card(shot: dict[str, Any]) -> None:
    image_path = image_path_of(shot)
    icon, text = copy_es.status_chip(shot["status"])
    rejected = shot["status"] in {"rejected_gate", "rejected_floor"}
    suffix = f" — {copy_es.discard_reason(shot)}" if rejected else ""
    st.markdown(f"{icon} **{text}**{suffix}")
    st.caption(
        f"{copy_es.clock(shot['start_time_seconds'])} · "
        f"{copy_es.duration_label(shot['duration_seconds'])}"
    )

    preview = preview_of(shot)
    if preview:
        st.image(preview, width="stretch")
    else:
        st.caption("Sin vista previa en este run.")

    actions = st.columns(2)
    if actions[0].button("Ver ficha", key=f"focus_{shot['shot_id']}", width="stretch"):
        st.session_state["simple_focus"] = shot["shot_id"]
        st.rerun()
    if image_path:
        actions[1].download_button(
            "Descargar",
            data=file_bytes(image_path, Path(image_path).stat().st_mtime),
            file_name=Path(image_path).name,
            mime="image/png",
            key=f"download_png_{shot['shot_id']}",
            width="stretch",
        )


def _select(shots: list[dict[str, Any]], filter_name: str, order: str) -> list[dict[str, Any]]:
    if filter_name == "Recomendados":
        chosen = [shot for shot in shots if shot["status"] == "selected"]
    elif filter_name == "Descartados":
        chosen = [shot for shot in shots if shot["status"].startswith("rejected")]
    else:
        chosen = list(shots)
    if order == "Por tiempo":
        return sorted(chosen, key=lambda shot: shot["start_time_seconds"])
    return sorted(
        chosen,
        key=lambda shot: (
            shot["status"] != "selected",
            -(shot.get("total_score") or 0.0),
            shot["start_time_seconds"],
        ),
    )


def render_results(
    document: dict[str, Any],
    result: dict[str, Any],
    config: dict[str, Any],
) -> None:
    summary = result["summary"]
    source = document["source"]
    recommended = summary["selected"]
    total = summary["total_shots"]

    st.subheader("Resultados")
    st.markdown(
        f"El vídeo dura **{copy_es.clock(source.get('duration_seconds', 0))}** y tiene "
        f"**{total} planos**. Este run recomienda **{recommended}**."
    )
    if recommended == 0:
        st.warning(
            "Ningún plano pasó los filtros. Baja la exigencia o cambia el tipo de foto "
            "en el panel lateral."
        )

    controls = st.columns([2, 2, 3])
    filter_name = controls[0].radio(
        "Mostrar",
        ["Recomendados", "Descartados", "Todos"],
        index=0,
        horizontal=False,
        key="simple_filter",
    )
    order = controls[1].selectbox(
        "Orden", ["Mejor primero", "Por tiempo"], key="simple_order"
    )

    shots = _select(result["shots"], filter_name, order)
    if not shots:
        st.info("No hay planos en esta vista.")
        return

    pages = max(1, (len(shots) + PAGE_SIZE - 1) // PAGE_SIZE)
    page = min(int(st.session_state.get("simple_page", 0)), pages - 1)
    if pages > 1:
        navigation = st.columns([1, 2, 1])
        if navigation[0].button("← Anterior", disabled=page <= 0, width="stretch"):
            st.session_state["simple_page"] = page - 1
            st.rerun()
        navigation[1].markdown(
            f"<div style='text-align:center'>Página {page + 1} de {pages} "
            f"({len(shots)} planos)</div>",
            unsafe_allow_html=True,
        )
        if navigation[2].button("Siguiente →", disabled=page >= pages - 1, width="stretch"):
            st.session_state["simple_page"] = page + 1
            st.rerun()

    window = shots[page * PAGE_SIZE : (page + 1) * PAGE_SIZE]
    for start in range(0, len(window), 3):
        columns = st.columns(3)
        for column, shot in zip(columns, window[start : start + 3], strict=False):
            with column, st.container(border=True):
                _card(shot)

    st.divider()
    downloads = st.columns([1, 1, 2])
    selected = [shot for shot in result["shots"] if shot["status"] == "selected"]
    exportable = [(shot, image_path_of(shot)) for shot in selected]
    exportable = [(shot, path) for shot, path in exportable if path]
    if exportable:
        paths = tuple(path for _, path in exportable)
        names = tuple(f"{shot['shot_id']}_{Path(path).name}" for shot, path in exportable)
        downloads[0].download_button(
            f"Descargar recomendadas (ZIP, {len(exportable)})",
            data=zip_bytes(paths, names),
            file_name=f"{document.get('run_id', 'run')}_recomendadas.zip",
            mime="application/zip",
            width="stretch",
        )
    else:
        downloads[0].caption("No hay fotos recomendadas para descargar.")
    downloads[1].download_button(
        "Descargar configuración (JSON)",
        data=json.dumps(config, indent=2, ensure_ascii=False),
        file_name="config_overrides.json",
        mime="application/json",
        width="stretch",
    )

    st.caption(
        "Las fotos se exportan a resolución completa. La configuración descargada "
        "reproduce este mismo ranking con el CLI."
    )


def render_sidebar(
    document: dict[str, Any],
    preferences: dict[str, Any],
    generation: int,
    *,
    apply_preset: Callable[[str], None],
    reset: Callable[[], None],
) -> None:
    st.sidebar.divider()
    st.sidebar.subheader("Qué buscas")

    names = [name for name in document["presets"] if name in copy_es.PRESET_CHOICES]
    names.sort(key=lambda name: name == "balanced_v1")
    current = preferences["preset"]
    index = names.index(current) if current in names else 0
    choice = st.sidebar.selectbox(
        "Tipo de foto",
        names,
        index=index,
        format_func=lambda name: copy_es.PRESET_CHOICES[name][0],
        key=f"simple_preset_{generation}",
    )
    st.sidebar.caption(copy_es.PRESET_CHOICES[choice][1])
    if choice != current:
        apply_preset(choice)
        st.rerun()

    shot_total = max(1, len(document["shots"]))
    options = [value for value in (5, 10, 20) if value <= shot_total] or [shot_total]
    current_n = int(preferences["top_n"])
    current_n = min(options, key=lambda value: abs(value - current_n))
    preferences["top_n"] = st.sidebar.selectbox(
        "Cuántas fotos",
        options,
        index=options.index(current_n),
        key=f"simple_topn_{generation}",
    )

    preferences["diversity"]["enabled"] = st.sidebar.toggle(
        "Que no se repitan escenas parecidas",
        value=bool(preferences["diversity"].get("enabled", True)),
        key=f"simple_div_{generation}",
        help="Aleja del Top-N los planos casi idénticos a uno ya elegido.",
    )

    st.sidebar.divider()
    if st.sidebar.button("Restablecer", width="stretch"):
        reset()
        st.rerun()
    st.sidebar.caption(
        "¿Necesitas afinar pesos, filtros o fronteras? Cambia a **Vista: Técnico**."
    )
