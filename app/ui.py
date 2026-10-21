"""Streamlit client for the shot technical selector.

This is a *view*: every number comes from ``video_dsp.selection_service``, so moving a
slider here and running the CLI with the exported config produce the same ranking.

Run it with:

    .\\.venv\\Scripts\\python.exe -m streamlit run app/ui.py

The client never decodes video. It reads ``ui.json`` and, only when the user changes the
boundary merge, ``samples.csv.gz``. All measurements are already on disk.
"""

from __future__ import annotations

import copy
import json
import os
import sys
from pathlib import Path
from typing import Any

APP_DIR = Path(__file__).resolve().parent
if str(APP_DIR) not in sys.path:
    # `streamlit run app/ui.py` already adds it; AppTest does not always. The client is a
    # script, not a package, so the sibling modules are imported flat.
    sys.path.insert(0, str(APP_DIR))

import altair as alt
import copy_es
import pandas as pd
import simple
import streamlit as st

from video_dsp.labels import (
    REJECT_REASONS,
    empty_labels,
    load_labels,
    record_boundary_label,
    record_pair_label,
    record_shot_label,
    save_labels,
    shot_labels,
)
from video_dsp.metrics_spec import DIMENSION_ORDER
from video_dsp.selection_service import build_shot_records, recompute
from video_dsp.shot_detection import distances_from_dicts, rebuild_shots

ROOT = Path(__file__).resolve().parents[1]
RUNS_DIR = Path(os.environ.get("VIDEO_DSP_RUNS_DIR", ROOT / "out" / "runs"))

STATUS_ES = {
    "selected": "Seleccionado",
    "passing_unselected": "Pasa, no elegido",
    "rejected_gate": "Rechazado por gate",
    "rejected_floor": "Bajo el piso de calidad",
}

STATUS_ORDER = ["selected", "passing_unselected", "rejected_gate", "rejected_floor"]

GATE_LABELS = {
    "min_sharpness_score": ("Nitidez mínima", "[0,1]", 0.0, 1.0, 0.01),
    "max_black_clip": ("Recorte de negros máx.", "fracción [0,1]", 0.0, 1.0, 0.01),
    "max_white_clip": ("Recorte de blancos máx.", "fracción [0,1]", 0.0, 1.0, 0.01),
    "max_instability": ("Inestabilidad máx.", "distancia [0,1]", 0.0, 1.0, 0.01),
    "max_jitter_px": ("Jitter máx.", "px por par", 0.0, 20.0, 0.1),
    "min_shot_duration_s": ("Duración mínima", "segundos", 0.0, 10.0, 0.1),
    "max_shot_duration_s": ("Duración máxima", "segundos", 0.0, 60.0, 0.5),
}

TARGET_ORDER = (
    "duration_seconds",
    "motion_per_second",
    "pan_speed_px_s",
    "saturation_mean",
)

TARGET_LABELS = {
    "duration_seconds": "Duración",
    "motion_per_second": "Cambio por segundo",
    "pan_speed_px_s": "Velocidad de paneo",
    "saturation_mean": "Saturación",
}


# --------------------------------------------------------------------------- data


@st.cache_data(show_spinner=False)
def load_ui(path: str) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


@st.cache_data(show_spinner=False, max_entries=16)
def load_image(path: str, mtime: float) -> bytes:
    """Bytes of an artifact image; ``mtime`` keys the cache to the file on disk."""
    del mtime
    return Path(path).read_bytes()


@st.cache_data(show_spinner="Cargando muestras…")
def load_samples(path: str) -> list[dict[str, Any]]:
    """Rebuild the sample list from ``samples.csv.gz`` (metrics + histogram)."""
    frame = pd.read_csv(path)
    histogram_columns = [column for column in frame.columns if column.startswith("hist_")]
    metric_columns = [
        column
        for column in frame.columns
        if column not in {"frame_index", "timestamp_seconds"}
        and not column.startswith("hist_")
    ]
    histograms = frame[histogram_columns].to_numpy(dtype=float)
    metrics = frame[metric_columns].to_numpy(dtype=float)
    frame_indices = frame["frame_index"].to_numpy(dtype=int)
    timestamps = frame["timestamp_seconds"].to_numpy(dtype=float)

    samples: list[dict[str, Any]] = []
    for position in range(len(frame)):
        sample_metrics = dict(zip(metric_columns, metrics[position].tolist(), strict=False))
        sample_metrics["histogram"] = histograms[position]
        samples.append(
            {
                "frame_index": int(frame_indices[position]),
                "timestamp_seconds": float(timestamps[position]),
                "metrics": sample_metrics,
            }
        )
    return samples


def find_runs() -> list[Path]:
    if not RUNS_DIR.exists():
        return []
    return sorted(
        (path.parent for path in RUNS_DIR.glob("*/ui.json")),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )


# ----------------------------------------------------------------------- preferences


def default_preferences(document: dict[str, Any]) -> dict[str, Any]:
    config = document["config"]
    return {
        "preset": config["preset"],
        "weights": {
            name: float(config["score_weights"].get(name, 0.0))
            for name in DIMENSION_ORDER
        },
        "gates": {
            key: float(config["hard_gates"][key])
            for key in GATE_LABELS
            if key in config["hard_gates"]
        },
        "targets": copy.deepcopy(config["targets"]),
        "floor": copy.deepcopy(config["quality_floor"]),
        "diversity": copy.deepcopy(config["diversity"]),
        "top_n": int(config["top_n"]),
        "merge_similarity": float(
            config.get("shot_detection", {}).get("merge_similarity", 1.0)
        ),
        "normalization_method": config["normalization"]["method"],
    }


def apply_preset(document: dict[str, Any], name: str) -> None:
    preset = document["presets"][name]
    preferences = st.session_state["prefs"]
    preferences["weights"] = {
        dimension: float(preset["weights"].get(dimension, 0.0))
        for dimension in DIMENSION_ORDER
    }
    preferences["targets"] = copy.deepcopy(preset["targets"])
    preferences["floor"] = copy.deepcopy(preset["quality_floor"])
    preferences["normalization_method"] = preset["normalization_method"]
    preferences["preset"] = name
    st.session_state["gen"] += 1


def reset_preferences(document: dict[str, Any]) -> None:
    """Back to the run's own config: the simple view must never keep stale knobs."""
    st.session_state["prefs"] = default_preferences(document)
    st.session_state["gen"] = st.session_state.get("gen", 0) + 1
    st.session_state.pop("simple_focus", None)
    st.session_state["simple_page"] = 0


def build_config(document: dict[str, Any], preferences: dict[str, Any]) -> dict[str, Any]:
    config = json.loads(json.dumps(document["config"]))
    config["preset"] = preferences["preset"]
    config["preset_label"] = document["presets"][preferences["preset"]]["label_es"]
    config["score_weights"] = dict(preferences["weights"])
    config["hard_gates"].update(preferences["gates"])
    config["targets"] = copy.deepcopy(preferences["targets"])
    config["quality_floor"] = dict(preferences["floor"])
    config["diversity"] = dict(preferences["diversity"])
    config["top_n"] = int(preferences["top_n"])
    config["shot_detection"]["merge_similarity"] = float(preferences["merge_similarity"])
    config["normalization"]["method"] = preferences["normalization_method"]
    return config


def compute_result(
    document: dict[str, Any],
    config: dict[str, Any],
    preferences: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Recompute the ranking, rebuilding shots only when the merge threshold moved."""
    merge = float(preferences["merge_similarity"])
    samples_path = document["artifacts"].get("samples_csv")
    distances = document.get("distances") or []
    if merge >= 0.9995 or not samples_path or not distances:
        return recompute(document["shots"], config), None

    samples = load_samples(samples_path)
    shots, evidence = rebuild_shots(
        samples,
        document.get("boundary_positions", []),
        merge_similarity=merge,
        min_duration=float(config["hard_gates"]["min_shot_duration_s"]),
        max_duration=float(config["hard_gates"]["max_shot_duration_s"]),
    )
    records = build_shot_records(shots, distances_from_dicts(distances), config)
    return recompute(records, config), evidence


# ---------------------------------------------------------------------------- utils


def shots_frame(result: dict[str, Any], catalog: dict[str, Any]) -> pd.DataFrame:
    rows = []
    for shot in result["shots"]:
        row = {
            "orden": shot.get("rank"),
            "plano": shot["shot_id"],
            "inicio": round(shot["start_time_seconds"], 2),
            "fin": round(shot["end_time_seconds"], 2),
            "dur": round(shot["duration_seconds"], 2),
            "total": round(shot["total_score"], 4),
        }
        for dimension in DIMENSION_ORDER:
            row[catalog[dimension]["label_es"]] = round(
                shot["dimension_scores"][dimension], 3
            )
        row["estado"] = STATUS_ES.get(shot["status"], shot["status"])
        row["motivo"] = shot.get("selection_reason", "")
        rows.append(row)
    return pd.DataFrame(rows)


def labels_path_for(document: dict[str, Any]) -> Path:
    existing = document["artifacts"].get("labels_json")
    if existing:
        return Path(existing)
    return Path(document["artifacts"]["run_dir"]) / "labels.json"


def current_labels(document: dict[str, Any]) -> dict[str, Any]:
    path = labels_path_for(document)
    if path.exists():
        try:
            return load_labels(path)
        except Exception as exc:  # noqa: BLE001 - surfaced to the user, never hidden
            st.warning(f"No se pudo leer {path.name}: {exc}. Se empieza de cero.")
    return empty_labels(
        annotator="local",
        video={
            "path": document["source"].get("path"),
            "file_hash_sha256": document["source"].get("file_hash_sha256"),
        },
    )


def persist_label(document: dict[str, Any], mutate) -> None:
    labels = current_labels(document)
    mutate(labels)
    save_labels(labels, labels_path_for(document))
    st.toast("Etiqueta guardada", icon="✅")


def component_rows(
    shot: dict[str, Any], normalization: dict[str, Any]
) -> list[dict[str, Any]]:
    rows = []
    for dimension in DIMENSION_ORDER:
        entry = normalization[dimension]
        scored = shot["component_scores"].get(dimension, {})
        for group in ("components", "fallback_components"):
            for component_id, component in entry[group].items():
                if component_id not in scored:
                    continue
                metric = component["metric"]
                raw = shot["metrics"].get(metric)
                rows.append(
                    {
                        "dimensión": entry["label_es"],
                        "componente": component["label_es"],
                        "variable": metric,
                        "unidad": component["unit_es"],
                        "bruto": None if raw is None else round(float(raw), 4),
                        "normalizado": round(float(scored[component_id]), 4),
                        "modo": component["mode"],
                        "método": component["method"],
                        "mín": round(float(component["low"]), 4),
                        "máx": round(float(component["high"]), 4),
                        "origen": component["source"],
                    }
                )
    return rows


def warning_banner(document: dict[str, Any], result: dict[str, Any]) -> None:
    calibration = document["config"]["hard_gates"].get("calibration", "")
    warnings = list(result.get("warnings", [])) + list(document.get("warnings", []))
    unique = list(dict.fromkeys(warnings))
    if calibration == "initial_uncalibrated":
        st.info(
            "Umbrales **sin calibrar** (`initial_uncalibrated`). Los números son "
            "coherentes entre sí, pero no están validados contra criterio humano. "
            "Usa las etiquetas para medir cuánto se acercan."
        )
    with st.expander(f"Avisos del run ({len(unique)})", expanded=False):
        if not unique:
            st.caption("Sin avisos.")
        for warning in unique:
            st.markdown(f"- `{warning}`")


def clear_shot_focus() -> None:
    st.session_state.pop("simple_focus", None)


@st.dialog("Ficha del plano", width="large", on_dismiss=clear_shot_focus)
def shot_dialog(
    document: dict[str, Any], result: dict[str, Any], shot_id: str
) -> None:
    shot_detail_panel(document, result, shot_id)


def shot_detail_panel(
    document: dict[str, Any], result: dict[str, Any], shot_id: str
) -> None:
    """Plain-language card for one shot, with the full evidence one click away."""
    shot = next((item for item in result["shots"] if item["shot_id"] == shot_id), None)
    if shot is None:
        st.info("Ese plano ya no existe con la configuración actual.")
        return

    title, close = st.columns([5, 1])
    title.subheader(f"Plano {shot_id}")
    if close.button("Cerrar", width="stretch", key="simple_detail_close"):
        clear_shot_focus()
        st.rerun()

    st.caption(
        f"Empieza en {copy_es.clock(shot['start_time_seconds'])} y dura "
        f"{copy_es.duration_label(shot['duration_seconds'])}."
    )
    icon, text = copy_es.status_chip(shot["status"])
    st.markdown(f"{icon} **{text}**")
    if shot["status"] in {"rejected_gate", "rejected_floor"}:
        st.caption(f"Motivo: {copy_es.discard_reason(shot)}.")
    st.markdown(
        copy_es.why_sentence(shot, shot.get("score_weights_effective", {}))
        + " La explicación se deriva del ranking; no es una valoración artística."
    )

    image_path = shot.get("selected_frame_image_path")
    left, right = st.columns([3, 2])
    with left:
        if image_path and Path(image_path).exists():
            image = Path(image_path)
            st.image(
                simple.preview_bytes(image_path, image.stat().st_mtime, 640),
                caption=(
                    f"Fotograma elegido en {copy_es.clock(shot['selected_frame_timestamp'])}. "
                    f"Regla: {shot.get('selected_frame_rule', 'sharpest')}."
                ),
                width=420,
            )
        else:
            st.info(
                "Este plano no tiene fotograma exportado en este run. Los "
                "representativos se escriben al generarlo; relanza el CLI para verlo."
            )
    with right:
        if image_path and Path(image_path).exists():
            image = Path(image_path)
            st.download_button(
                "Descargar foto (PNG)",
                data=simple.file_bytes(image_path, image.stat().st_mtime),
                file_name=image.name,
                mime="image/png",
                width="stretch",
                key=f"simple_detail_dl_{shot_id}",
            )
        failures = shot.get("failed_gates") or []
        if failures:
            st.markdown("**Filtros que no pasó**")
            st.dataframe(
                pd.DataFrame(
                    [
                        {
                            "filtro": item["gate"],
                            "valor": item.get("value"),
                            "umbral": item.get("threshold"),
                        }
                        for item in failures
                    ]
                ),
                hide_index=True,
                width="stretch",
            )
        else:
            st.markdown("**Filtros**")
            st.caption("Pasó todos los filtros activos.")
        score = f"{shot.get('total_score', 0):.3f}".replace(".", ",")
        st.caption(f"Puntuación total: {score} sobre 1.")

    with st.expander("Ver detalle técnico (variables, unidades y normalización)"):
        st.dataframe(
            pd.DataFrame(component_rows(shot, result["normalization"])),
            hide_index=True,
            width="stretch",
        )
        st.caption(
            "Cada fila declara variable, unidad, valor bruto, valor normalizado y el "
            "rango usado. Los valores que faltan aparecen como «no disponible»."
        )


# ----------------------------------------------------------------------------- app


def main() -> None:
    st.set_page_config(
        page_title="Selector de planos",
        page_icon="🎬",
        layout="wide",
    )

    runs = find_runs()
    if not runs:
        st.title("Selector de planos")
        st.error(
            "No hay runs disponibles. Ejecuta primero:\n\n"
            "```\n.\\\\.venv\\\\Scripts\\\\python.exe -m video_dsp.cli "
            '"C:\\\\ruta\\\\video.mp4"\n```'
        )
        st.stop()

    st.sidebar.title("🎬 Selector de planos")
    mode = st.sidebar.radio(
        "Vista",
        ["Simple", "Técnico"],
        index=0,
        horizontal=True,
        key="ui_mode",
        help=(
            "Simple: solo lo esencial, con las fotos y sus descargas. "
            "Técnico: todos los pesos, gates y evidencias."
        ),
    )
    run_labels = {path: f"{path.name}" for path in runs}
    selected_run = st.sidebar.selectbox(
        "Run",
        options=runs,
        format_func=lambda path: run_labels[path],
        index=0,
    )
    document = load_ui(str(selected_run / "ui.json"))

    if st.session_state.get("run_path") != str(selected_run):
        st.session_state["run_path"] = str(selected_run)
        st.session_state["prefs"] = default_preferences(document)
        st.session_state["gen"] = st.session_state.get("gen", 0) + 1
        st.session_state.pop("shot_choice", None)
        st.session_state.pop("simple_focus", None)
        st.session_state["simple_page"] = 0

    preferences = st.session_state["prefs"]
    generation = st.session_state.get("gen", 0)

    source = document["source"]
    st.sidebar.caption(
        f"`{Path(source.get('path', '?')).name}` · "
        f"{source.get('duration_seconds', 0):.1f}s · "
        f"{source.get('width')}×{source.get('height')} · "
        f"{source.get('codec')}"
    )

    config = build_config(document, preferences)
    if mode == "Simple":
        simple.render_sidebar(
            document,
            preferences,
            generation,
            apply_preset=lambda name: apply_preset(document, name),
            reset=lambda: reset_preferences(document),
        )
    else:
        render_sidebar(document, preferences, generation)

    config = build_config(document, preferences)
    with st.spinner("Recalculando ranking…"):
        result, rebuild_evidence = compute_result(document, config, preferences)

    if mode == "Simple":
        st.title("Tus fotos")
        warning_banner(document, result)
        simple.render_results(document, result, config)
        if st.session_state.get("simple_focus"):
            shot_dialog(document, result, st.session_state["simple_focus"])
        return

    header(document, result)
    warning_banner(document, result)

    tabs = st.tabs(
        [
            "Calibración",
            "Ranking y gates",
            "Fronteras",
            "Distribuciones",
            "Resumen",
            "Auditoría",
        ]
    )
    with tabs[0]:
        tab_calibration(document, result, preferences, generation)
    with tabs[1]:
        tab_ranking(document, result)
    with tabs[2]:
        tab_boundaries(document, result, preferences, generation, rebuild_evidence)
    with tabs[3]:
        tab_distributions(document, result)
    with tabs[4]:
        tab_summary(document, result)
    with tabs[5]:
        tab_audit(document, result, config)


def header(document: dict[str, Any], result: dict[str, Any]) -> None:
    summary = result["summary"]
    columns = st.columns(5)
    columns[0].metric("Planos", summary["total_shots"])
    columns[1].metric("Pasan gates", summary["passed_gates"])
    columns[2].metric("Seleccionados", summary["selected"])
    columns[3].metric("Rechazados", summary["rejected_gate"] + summary["rejected_floor"])
    columns[4].metric("Mejor score", f"{summary['top_score']:.3f}")
    st.caption(
        f"Preset `{result['preferences']['preset']}` · "
        f"normalización `{result['preferences']['normalization_method']}` · "
        f"diversidad `{summary['diversity_weight']:.2f}` · "
        f"config `{document['config_hash'][:18]}…`"
    )


def render_sidebar(
    document: dict[str, Any], preferences: dict[str, Any], generation: int
) -> None:
    st.sidebar.divider()
    st.sidebar.subheader("Preset")

    preset_names = list(document["presets"])
    current = preferences["preset"]
    index = preset_names.index(current) if current in preset_names else 0
    choice = st.sidebar.selectbox(
        "Preferencia base", preset_names, index=index, key="preset_select"
    )
    st.sidebar.caption(document["presets"][choice]["description_es"])
    if st.sidebar.button("Aplicar preset", width="stretch"):
        apply_preset(document, choice)
        st.rerun()
    normalize = st.sidebar.toggle(
        "Normalizar por vídeo (p5-p95)",
        value=preferences["normalization_method"] == "per_video_percentile",
        key=f"norm_toggle_{generation}",
        help=(
            "Activado: los rangos salen de la distribución de este vídeo. "
            "Desactivado: rangos absolutos del config (reproduce balanced_v1)."
        ),
    )
    preferences["normalization_method"] = (
        "per_video_percentile" if normalize else "absolute"
    )

    st.sidebar.divider()
    st.sidebar.subheader("Pesos")
    total = 0.0
    for dimension in DIMENSION_ORDER:
        label = document["dimension_catalog"][dimension]["label_es"]
        preferences["weights"][dimension] = st.sidebar.slider(
            label,
            min_value=0.0,
            max_value=1.0,
            value=float(preferences["weights"][dimension]),
            step=0.01,
            key=f"w_{dimension}_{generation}",
            help=document["dimension_catalog"][dimension]["description_es"],
        )
        total += preferences["weights"][dimension]
    if total <= 0:
        st.sidebar.error("Todos los pesos están a cero.")
    else:
        st.sidebar.caption(f"Suma de pesos: {total:.2f} (se renormaliza a 1.0)")

    st.sidebar.divider()
    st.sidebar.subheader("Selección")
    shot_total = max(1, len(document["shots"]))
    preferences["top_n"] = st.sidebar.number_input(
        "Top-N",
        min_value=1,
        max_value=shot_total,
        value=min(max(1, int(preferences["top_n"])), shot_total),
        step=1,
        key=f"topn_{generation}",
    )
    preferences["diversity"]["enabled"] = st.sidebar.toggle(
        "Penalizar duplicados (MMR)",
        value=bool(preferences["diversity"].get("enabled", True)),
        key=f"div_on_{generation}",
        help="Aleja del Top-N los planos casi idénticos a uno ya elegido.",
    )
    preferences["diversity"]["weight"] = st.sidebar.slider(
        "Fuerza de diversidad",
        min_value=0.0,
        max_value=0.9,
        value=float(preferences["diversity"].get("weight", 0.25)),
        step=0.05,
        key=f"div_w_{generation}",
        disabled=not preferences["diversity"]["enabled"],
    )

    st.sidebar.divider()
    with st.sidebar.expander("Gates", expanded=False):
        for key, (label, unit, low, high, step) in GATE_LABELS.items():
            if key not in preferences["gates"]:
                continue
            preferences["gates"][key] = st.number_input(
                f"{label} ({unit})",
                min_value=low,
                max_value=high,
                value=float(preferences["gates"][key]),
                step=step,
                key=f"gate_{key}_{generation}",
            )

    with st.sidebar.expander("Bandas objetivo", expanded=False):
        st.caption(
            "Dentro de la banda la puntuación es 1.0; fuera cae linealmente "
            "según el margen."
        )
        for target in TARGET_ORDER:
            band = preferences["targets"].get(target)
            if not band:
                continue
            columns = st.columns(2)
            band["low"] = columns[0].number_input(
                f"{TARGET_LABELS[target]} mín.",
                value=float(band["low"]),
                step=0.5 if target == "duration_seconds" else 0.05,
                key=f"tgt_lo_{target}_{generation}",
            )
            band["high"] = columns[1].number_input(
                f"{TARGET_LABELS[target]} máx.",
                value=float(band["high"]),
                step=0.5 if target == "duration_seconds" else 0.05,
                key=f"tgt_hi_{target}_{generation}",
            )
            band["falloff"] = st.number_input(
                f"{TARGET_LABELS[target]} margen",
                min_value=0.01,
                value=float(band.get("falloff", 0.5)),
                step=0.05,
                key=f"tgt_fo_{target}_{generation}",
            )

    with st.sidebar.expander("Piso de calidad", expanded=False):
        preferences["floor"]["enabled"] = st.checkbox(
            "Activo",
            value=bool(preferences["floor"].get("enabled", True)),
            key=f"floor_on_{generation}",
        )
        preferences["floor"]["min_total_score"] = st.slider(
            "Score mínimo",
            min_value=0.0,
            max_value=1.0,
            value=float(preferences["floor"].get("min_total_score", 0.25)),
            step=0.01,
            key=f"floor_v_{generation}",
            disabled=not preferences["floor"]["enabled"],
        )

    st.sidebar.divider()
    if st.sidebar.button("Restablecer", width="stretch"):
        st.session_state["prefs"] = default_preferences(document)
        st.session_state["gen"] = generation + 1
        st.rerun()

    st.sidebar.download_button(
        "Descargar config (JSON)",
        data=json.dumps(build_config(document, preferences), indent=2, ensure_ascii=False),
        file_name="config_overrides.json",
        mime="application/json",
        width="stretch",
        help="Pásalo al CLI con --config para reproducir exactamente este ranking.",
    )


# ------------------------------------------------------------------------- tab: calib


def tab_calibration(
    document: dict[str, Any],
    result: dict[str, Any],
    preferences: dict[str, Any],
    generation: int,
) -> None:
    selected = result["selected"]
    base_ids = [shot["shot_id"] for shot in document["selected"]]
    now_ids = [shot["shot_id"] for shot in selected]
    entered = [shot_id for shot_id in now_ids if shot_id not in base_ids]
    dropped = [shot_id for shot_id in base_ids if shot_id not in now_ids]
    reordered = not entered and not dropped and now_ids != base_ids

    st.subheader("Qué estáis premiando")
    left, right = st.columns([3, 2])

    with left:
        weights = pd.DataFrame(
            {
                "dimensión": [
                    document["dimension_catalog"][dimension]["label_es"]
                    for dimension in DIMENSION_ORDER
                ],
                "peso": [preferences["weights"][dimension] for dimension in DIMENSION_ORDER],
                "score medio elegidos": [
                    _mean([shot["dimension_scores"][dimension] for shot in selected])
                    for dimension in DIMENSION_ORDER
                ],
            }
        )
        weights["aporte"] = weights["peso"] * weights["score medio elegidos"]
        chart = (
            alt.Chart(weights)
            .mark_bar()
            .encode(
                x=alt.X("aporte:Q", title="aporte al score (peso × score medio)"),
                y=alt.Y("dimensión:N", sort="-x", title=None),
                tooltip=["dimensión", "peso", "score medio elegidos", "aporte"],
            )
            .properties(height=260)
        )
        st.altair_chart(chart, width="stretch")
        st.caption(
            "El aporte explica por qué gana el Top-N actual. Si una dimensión con poco "
            "peso domina el aporte, el score medio de los elegidos es alto y el peso no "
            "es el problema."
        )

    with right:
        st.metric(
            "Cambios respecto al run del CLI",
            len(entered) + len(dropped),
            help="Planos que entran o salen del Top-N con tus pesos actuales.",
        )
        if entered or dropped:
            rank_of = {shot["shot_id"]: shot["rank"] for shot in selected}
            rows = [
                {"movimiento": "entra", "plano": shot_id, "orden": rank_of[shot_id]}
                for shot_id in entered
            ]
            rows.extend(
                {"movimiento": "sale", "plano": shot_id, "orden": None}
                for shot_id in dropped
            )
            st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
        elif reordered:
            st.caption("Mismo conjunto de planos, distinto orden.")
        else:
            st.caption("Idéntico al run guardado.")

    st.divider()
    st.subheader("Top-N con tus pesos")
    table = shots_frame(result, document["dimension_catalog"])
    table = table[table["orden"].notna()].sort_values("orden")
    st.dataframe(table, hide_index=True, width="stretch")

    st.divider()
    left, right = st.columns([1, 1])
    with left:
        st.subheader("Ficha de un plano")
        options = [shot["shot_id"] for shot in result["shots"]]
        chosen = st.selectbox("Plano", options, key=f"cal_shot_{generation}")
        shot = next(item for item in result["shots"] if item["shot_id"] == chosen)
        st.dataframe(
            pd.DataFrame(component_rows(shot, result["normalization"])),
            hide_index=True,
            width="stretch",
        )
    with right:
        st.subheader("Fotograma representativo")
        image_path = shot.get("selected_frame_image_path")
        if image_path and Path(image_path).exists():
            image = Path(image_path)
            st.image(image_path, width="stretch")
            st.caption(
                f"{shot['shot_id']} · t={shot['selected_frame_timestamp']:.2f}s · "
                f"regla: `{shot.get('selected_frame_rule', 'sharpest')}`"
            )
            st.download_button(
                "Descargar fotograma (PNG)",
                data=load_image(str(image), image.stat().st_mtime),
                file_name=image.name,
                mime="image/png",
                width="stretch",
                key=f"download_frame_{generation}_{shot['shot_id']}",
            )
            st.caption(f"Archivo: `{image_path}`")
        else:
            st.info(
                "Este plano no tiene fotograma exportado con el corte actual. Los "
                "representativos se escriben al generar el run; si cambiaste la fusión "
                "de fronteras, relanza el CLI con ese `--merge-similarity` para "
                "exportarlos."
            )

    st.divider()
    calibration_pairs(document, result)


def calibration_pairs(document: dict[str, Any], result: dict[str, Any]) -> None:
    st.subheader("Comparación por parejas (nivel B)")
    st.caption(
        "Elige cuál de los dos planos es mejor para ti. Es la señal que revela si los "
        "pesos están mal: no se aplica sola, se guarda en labels.json y se mide."
    )
    labels = current_labels(document)
    shot_ids = [shot["shot_id"] for shot in result["shots"]]
    if len(shot_ids) < 2:
        st.info("Hacen falta al menos dos planos.")
        return

    left, right = st.columns(2)
    with left:
        option_a = st.selectbox("Plano A", shot_ids, index=0, key="pair_a")
    with right:
        option_b = st.selectbox(
            "Plano B",
            shot_ids,
            index=min(1, len(shot_ids) - 1),
            key="pair_b",
        )
    if option_a == option_b:
        st.warning("Elige dos planos distintos.")
        return

    columns = st.columns(4)
    if columns[0].button("Gana A", width="stretch", key="pair_pick_a"):
        persist_label(
            document,
            lambda document_labels: record_pair_label(
                document_labels, a=option_a, b=option_b, winner="a"
            ),
        )
        st.rerun()
    if columns[1].button("Gana B", width="stretch", key="pair_pick_b"):
        persist_label(
            document,
            lambda document_labels: record_pair_label(
                document_labels, a=option_b, b=option_a, winner="a"
            ),
        )
        st.rerun()
    if columns[2].button("Empate", width="stretch", key="pair_pick_tie"):
        persist_label(
            document,
            lambda document_labels: record_pair_label(
                document_labels, a=option_a, b=option_b, winner="tie"
            ),
        )
        st.rerun()

    scores = {shot["shot_id"]: shot["total_score"] for shot in result["shots"]}
    pair_rows = []
    correct = 0
    compared = 0
    for pair in labels.get("pairs", []):
        a_score = scores.get(pair["a"])
        b_score = scores.get(pair["b"])
        if a_score is None or b_score is None:
            continue
        predicted = "a" if a_score > b_score else ("b" if b_score > a_score else "tie")
        if pair["winner"] != "tie":
            compared += 1
            correct += int(predicted == pair["winner"])
        pair_rows.append(
            {
                "A": pair["a"],
                "B": pair["b"],
                "tu elección": pair["winner"],
                "score A": round(a_score, 4),
                "score B": round(b_score, 4),
                "acierta": predicted == pair["winner"],
            }
        )
    if compared:
        st.metric(
            "Acierto de los pesos actuales",
            f"{correct / compared:.0%}",
            help=f"{correct} de {compared} parejas ordenadas igual que tú.",
        )
    if pair_rows:
        st.dataframe(pd.DataFrame(pair_rows), hide_index=True, width="stretch")
    else:
        st.caption("Todavía no hay parejas etiquetadas.")


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


# ----------------------------------------------------------------------- tab: ranking


def tab_ranking(document: dict[str, Any], result: dict[str, Any]) -> None:
    st.subheader("Todos los planos")
    table = shots_frame(result, document["dimension_catalog"])
    table["estado_crudo"] = [shot["status"] for shot in result["shots"]]

    statuses = st.multiselect(
        "Filtrar por estado",
        options=STATUS_ORDER,
        default=STATUS_ORDER,
        format_func=lambda value: STATUS_ES[value],
    )
    filtered = table[table["estado_crudo"].isin(statuses)].drop(columns=["estado_crudo"])
    st.caption(f"{len(filtered)} de {len(table)} planos.")
    st.dataframe(filtered, hide_index=True, width="stretch")

    st.divider()
    st.subheader("Detalle y gates")
    options = [shot["shot_id"] for shot in result["shots"]]
    chosen = st.selectbox("Plano", options, key="rank_shot")
    shot = next(item for item in result["shots"] if item["shot_id"] == chosen)

    columns = st.columns(4)
    columns[0].metric("Score total", f"{shot['total_score']:.4f}")
    columns[1].metric("Estado", STATUS_ES.get(shot["status"], shot["status"]))
    columns[2].metric("Duración", f"{shot['duration_seconds']:.2f}s")
    columns[3].metric("Estabilidad vía", shot.get("stability_source", "translation"))

    if shot["failed_gates"]:
        st.error(
            "Rechazado por: "
            + ", ".join(failure["gate"] for failure in shot["failed_gates"])
        )
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "gate": failure["gate"],
                        "valor": round(failure["value"], 4),
                        "umbral": round(failure["threshold"], 4),
                        "lectura": failure["interpretation"],
                    }
                    for failure in shot["failed_gates"]
                ]
            ),
            hide_index=True,
            width="stretch",
        )
    else:
        st.success("Pasa todos los gates.")

    left, right = st.columns(2)
    with left:
        st.markdown("**Métricas brutas**")
        rows = [
            {
                "variable": key,
                "etiqueta": document["field_catalog"].get(key, {}).get("label_es", key),
                "valor": round(float(value), 5),
                "unidad": document["field_catalog"].get(key, {}).get("unit_es", ""),
            }
            for key, value in sorted(shot["metrics"].items())
        ]
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch", height=320)
    with right:
        st.markdown("**Normalizado y de dónde sale**")
        st.dataframe(
            pd.DataFrame(component_rows(shot, result["normalization"])),
            hide_index=True,
            width="stretch",
            height=320,
        )

    st.divider()
    annotation_panel(document, shot)


def annotation_panel(document: dict[str, Any], shot: dict[str, Any]) -> None:
    st.subheader("Anotación (nivel A)")
    labels = current_labels(document)
    existing = shot_labels(labels).get(shot["shot_id"], {})
    current = existing.get("verdict", "sin etiquetar")

    reason = st.selectbox(
        "Motivo del descarte",
        REJECT_REASONS,
        key=f"reason_{shot['shot_id']}",
        index=REJECT_REASONS.index(existing["reason"])
        if existing.get("reason") in REJECT_REASONS
        else 0,
    )

    columns = st.columns(4)
    if columns[0].button(
        "Mantener", width="stretch", type="primary", key=f"keep_{shot['shot_id']}"
    ):
        persist_label(
            document,
            lambda document_labels: record_shot_label(
                document_labels, shot_id=shot["shot_id"], verdict="keep"
            ),
        )
        st.rerun()
    if columns[1].button("Descartar", width="stretch", key=f"reject_{shot['shot_id']}"):
        persist_label(
            document,
            lambda document_labels: record_shot_label(
                document_labels,
                shot_id=shot["shot_id"],
                verdict="reject",
                reason=reason,
            ),
        )
        st.rerun()
    if columns[2].button("Dudoso", width="stretch", key=f"unsure_{shot['shot_id']}"):
        persist_label(
            document,
            lambda document_labels: record_shot_label(
                document_labels, shot_id=shot["shot_id"], verdict="unsure"
            ),
        )
        st.rerun()

    st.caption(f"Etiqueta actual: **{current}**")


# ---------------------------------------------------------------------- tab: borders


def tab_boundaries(
    document: dict[str, Any],
    result: dict[str, Any],
    preferences: dict[str, Any],
    generation: int,
    rebuild_evidence: dict[str, Any] | None,
) -> None:
    st.subheader("Sobre-segmentación")
    st.caption(
        "Fusiona planos adyacentes casi idénticos. Se recalcula de verdad: reconstruye "
        "los planos desde las muestras y vuelve a medir, no aproxima."
    )
    has_samples = bool(document["artifacts"].get("samples_csv")) and bool(
        document.get("distances")
    )
    preferences["merge_similarity"] = st.slider(
        "Similitud mínima para fusionar (Bhattacharyya)",
        min_value=0.90,
        max_value=1.0,
        value=float(preferences["merge_similarity"]),
        step=0.005,
        key=f"merge_{generation}",
        disabled=not has_samples,
        help="1.0 desactiva la fusión. 0.98 fusiona solo planos casi idénticos.",
    )
    if not has_samples:
        st.warning(
            "Este run no tiene samples.csv.gz o distancias; regenera con artefactos "
            "activados para usar el control de fusión."
        )

    detection = document.get("boundary_detection", {})
    columns = st.columns(4)
    columns[0].metric("Fronteras detectadas", len(document.get("boundary_positions", [])))
    columns[1].metric("Umbral MAD", f"{detection.get('threshold', 0.0):.4f}")
    columns[2].metric("Planos actuales", result["summary"]["total_shots"])
    if rebuild_evidence:
        columns[3].metric(
            "Planos sin fusionar",
            rebuild_evidence["shots_built"],
            delta=result["summary"]["total_shots"] - rebuild_evidence["shots_built"],
        )
    else:
        columns[3].metric("Fusión", "desactivada")

    candidates = detection.get("peaks_before_prominence")
    rejected_peaks = detection.get("rejected_peaks", [])
    if candidates is not None:
        st.caption(
            f"Picos candidatos: **{candidates}** · descartados por baja prominencia: "
            f"**{len(rejected_peaks)}** · factor exigido: "
            f"{detection.get('prominence_ratio', 0.0):.2f}× sobre la mediana local "
            f"(radio {detection.get('prominence_radius', 'no disponible')} muestras, "
            f"guarda {detection.get('prominence_guard', 'no disponible')}). Un máximo "
            "dentro de una moción sostenida no es un cambio de contenido."
        )
        if rejected_peaks:
            with st.expander("Picos descartados (moción sostenida, no corte)"):
                st.dataframe(
                    pd.DataFrame(
                        [
                            {
                                "t (s)": (
                                    round(record["time_mid_seconds"], 2)
                                    if record.get("time_mid_seconds") is not None
                                    else "no disponible"
                                ),
                                "distancia": record.get("combined"),
                                "referencia local": record.get("local_reference"),
                                "prominencia": record.get("prominence_ratio"),
                                "motivo": record.get("reason"),
                            }
                            for record in rejected_peaks
                        ]
                    ),
                    width="stretch",
                    hide_index=True,
                )

    st.divider()
    st.subheader("Evidencia por frontera")
    montages = document.get("boundaries", [])
    if not montages:
        st.info("Este run no generó montajes de frontera.")
        return

    labels = current_labels(document)
    boundary_map = {
        entry["boundary_id"]: entry for entry in labels.get("boundaries", [])
    }
    index = st.slider(
        "Frontera",
        min_value=1,
        max_value=len(montages),
        value=1,
        step=1,
        key="boundary_index",
    )
    montage = montages[index - 1]
    if montage.get("path") and Path(montage["path"]).exists():
        montage_file = Path(montage["path"])
        st.image(montage["path"], width="stretch")
        st.download_button(
            "Descargar montaje (PNG)",
            data=load_image(str(montage_file), montage_file.stat().st_mtime),
            file_name=montage_file.name,
            mime="image/png",
            key=f"download_montage_{montage['boundary_id']}",
        )
    st.caption(
        f"t={montage['time_mid_seconds']:.3f}s · "
        f"fuerza={montage.get('combined')} · "
        f"offset={montage['offsets_seconds']}"
    )

    existing = boundary_map.get(montage["boundary_id"], {})
    columns = st.columns(3)
    if columns[0].button("Corte real", width="stretch", key="boundary_real"):
        persist_label(
            document,
            lambda document_labels: record_boundary_label(
                document_labels,
                boundary_id=montage["boundary_id"],
                verdict="real_cut",
            ),
        )
        st.rerun()
    if columns[1].button("Falso positivo", width="stretch", key="boundary_false"):
        persist_label(
            document,
            lambda document_labels: record_boundary_label(
                document_labels,
                boundary_id=montage["boundary_id"],
                verdict="false_positive",
            ),
        )
        st.rerun()
    if columns[2].button("Dudoso", width="stretch", key="boundary_unsure"):
        persist_label(
            document,
            lambda document_labels: record_boundary_label(
                document_labels,
                boundary_id=montage["boundary_id"],
                verdict="unsure",
            ),
        )
        st.rerun()
    st.caption(f"Etiqueta actual: **{existing.get('verdict', 'sin etiquetar')}**")

    labeled = sum(
        1 for entry in labels.get("boundaries", []) if entry.get("verdict") != "unsure"
    )
    if labeled:
        false_positives = sum(
            1
            for entry in labels.get("boundaries", [])
            if entry.get("verdict") == "false_positive"
        )
        st.metric(
            "Fronteras etiquetadas",
            f"{labeled} / {len(montages)}",
            help=f"{false_positives} marcadas como falso positivo.",
        )


# -------------------------------------------------------------------- tab: distribu


def tab_distributions(document: dict[str, Any], result: dict[str, Any]) -> None:
    st.subheader("Distribución de una variable")
    metric_keys = sorted(
        key
        for key in document["field_catalog"]
        if result["shots"] and key in result["shots"][0]["metrics"]
    )
    metric = st.selectbox(
        "Variable",
        metric_keys,
        index=metric_keys.index("variance_laplacian")
        if "variance_laplacian" in metric_keys
        else 0,
    )
    meta = document["field_catalog"][metric]
    st.caption(
        f"**{meta['label_es']}** · unidad: `{meta['unit_es']}` · agregación: "
        f"`{meta['aggregation']}` · medida en: {meta['measured_on']}. {meta['description_es']}"
    )

    frame = pd.DataFrame(
        {
            "valor": [shot["metrics"][metric] for shot in result["shots"]],
            "estado": [
                STATUS_ES.get(shot["status"], shot["status"]) for shot in result["shots"]
            ],
            "plano": [shot["shot_id"] for shot in result["shots"]],
        }
    )
    base = alt.Chart(frame)
    histogram = (
        base.mark_bar(opacity=0.75)
        .encode(
            x=alt.X("valor:Q", bin=alt.Bin(maxbins=24), title=meta["label_es"]),
            y=alt.Y("count()", title="planos"),
            color=alt.Color("estado:N", title="estado"),
            tooltip=["count()", "estado"],
        )
        .properties(height=280)
    )
    st.altair_chart(histogram, width="stretch")

    bounds = _bounds_for(result["normalization"], metric)
    if bounds:
        st.caption(
            f"Rangos usados en la normalización: `{bounds['method']}` · "
            f"mín={bounds['low']:.4f} · máx={bounds['high']:.4f} · "
            f"origen=`{bounds['source']}`"
        )
        rules = pd.DataFrame({"x": [bounds["low"], bounds["high"]]})
        rule_chart = (
            alt.Chart(rules)
            .mark_rule(strokeDash=[4, 4], color="#d62728")
            .encode(x="x:Q")
            .properties(height=280)
        )
        st.altair_chart((histogram + rule_chart), width="stretch")
    else:
        st.caption("Esta variable no participa en la normalización de ninguna dimensión.")

    st.divider()
    st.subheader("Dispersión entre dos variables")
    columns = st.columns(2)
    x_metric = columns[0].selectbox("Eje X", metric_keys, index=0, key="scatter_x")
    y_metric = columns[1].selectbox(
        "Eje Y",
        metric_keys,
        index=min(len(metric_keys) - 1, metric_keys.index("instability"))
        if "instability" in metric_keys
        else 0,
        key="scatter_y",
    )
    scatter_frame = pd.DataFrame(
        {
            "x": [shot["metrics"][x_metric] for shot in result["shots"]],
            "y": [shot["metrics"][y_metric] for shot in result["shots"]],
            "estado": [
                STATUS_ES.get(shot["status"], shot["status"]) for shot in result["shots"]
            ],
            "plano": [shot["shot_id"] for shot in result["shots"]],
            "total": [shot["total_score"] for shot in result["shots"]],
        }
    )
    scatter = (
        alt.Chart(scatter_frame)
        .mark_circle(size=70)
        .encode(
            x=alt.X("x:Q", title=document["field_catalog"][x_metric]["label_es"]),
            y=alt.Y("y:Q", title=document["field_catalog"][y_metric]["label_es"]),
            color=alt.Color("estado:N", title="estado"),
            tooltip=["plano", "estado", "total", "x", "y"],
        )
        .properties(height=320)
        .interactive()
    )
    st.altair_chart(scatter, width="stretch")
    st.caption(
        f"X: {document['field_catalog'][x_metric]['unit_es']} · "
        f"Y: {document['field_catalog'][y_metric]['unit_es']}. "
        "Color = estado tras gates y piso de calidad."
    )


def _bounds_for(normalization: dict[str, Any], metric: str) -> dict[str, Any] | None:
    for dimension in normalization.values():
        for group in ("components", "fallback_components"):
            for component in dimension[group].values():
                if component["metric"] == metric:
                    return component
    return None


# ------------------------------------------------------------------------ tab: summary


def tab_summary(document: dict[str, Any], result: dict[str, Any]) -> None:
    summary = result["summary"]
    st.subheader("Resumen del run")
    left, right = st.columns([3, 2])
    with left:
        st.dataframe(
            pd.DataFrame(
                [
                    {"campo": "Planos", "valor": str(summary["total_shots"])},
                    {"campo": "Pasan gates", "valor": str(summary["passed_gates"])},
                    {"campo": "Seleccionados", "valor": str(summary["selected"])},
                    {
                        "campo": "Pasan, no elegidos",
                        "valor": str(summary["passing_unselected"]),
                    },
                    {
                        "campo": "Rechazados por gate",
                        "valor": str(summary["rejected_gate"]),
                    },
                    {"campo": "Bajo el piso", "valor": str(summary["rejected_floor"])},
                    {"campo": "Preset", "valor": str(summary["preset"])},
                    {
                        "campo": "Diversidad",
                        "valor": f"{summary['diversity_weight']:.2f}",
                    },
                    {
                        "campo": "Mejor score",
                        "valor": f"{summary['top_score']:.4f}",
                    },
                ]
            ),
            hide_index=True,
            width="stretch",
        )
    with right:
        selected = result["selected"]
        if selected:
            st.markdown("**Top-N**")
            st.dataframe(
                pd.DataFrame(
                    [
                        {
                            "orden": shot["rank"],
                            "plano": shot["shot_id"],
                            "inicio": round(shot["start_time_seconds"], 2),
                            "fin": round(shot["end_time_seconds"], 2),
                            "score": round(shot["total_score"], 4),
                        }
                        for shot in selected
                    ]
                ),
                hide_index=True,
                width="stretch",
            )
        if summary["displaced_by_diversity"]:
            st.caption(
                "Desplazados por diversidad: "
                + ", ".join(summary["displaced_by_diversity"])
            )

    st.divider()
    st.markdown("**Cómo leer esto**")
    st.markdown(
        "- El score es una mezcla ponderada de 8 dimensiones, cada una normalizada con "
        "los rangos que aparecen en *Distribuciones*.\n"
        "- Un plano puede pasar los gates y quedar fuera del Top-N: no es un rechazo, "
        "es competencia.\n"
        "- `initial_uncalibrated` significa que los umbrales son una hipótesis de "
        "trabajo, no una verdad medida. Las etiquetas de nivel A y B son las que "
        "permiten corregirlos.\n"
        "- Nada de esto es un juicio editorial: es un borrador técnico."
    )

    st.divider()
    st.subheader("Evaluación contra tus etiquetas")
    evaluation = document.get("evaluation")
    if evaluation is None:
        st.info(
            "Este run se generó sin labels.json. Anota planos en *Ranking y gates* y "
            "vuelve a lanzar el CLI con `--labels` para obtener precisión, recall y "
            "NDCG."
        )
        return
    if evaluation["status"] != "ok":
        st.warning("Etiquetas insuficientes: " + "; ".join(evaluation["warnings"]))
        return
    metrics = evaluation["metrics"]
    columns = st.columns(4)
    columns[0].metric(
        "Precisión@N",
        "—" if metrics["precision_at_n"] is None else f"{metrics['precision_at_n']:.2f}",
    )
    columns[1].metric(
        "Recall de 'keep'",
        "—" if metrics["recall_keep"] is None else f"{metrics['recall_keep']:.2f}",
    )
    columns[2].metric(
        "NDCG@N",
        "—" if metrics["ndcg_at_n"] is None else f"{metrics['ndcg_at_n']:.2f}",
    )
    columns[3].metric(
        "Acierto parejas",
        "—"
        if evaluation["pairwise"]["accuracy"] is None
        else f"{evaluation['pairwise']['accuracy']:.0%}",
    )
    if evaluation["gate_diagnostics"]:
        st.markdown("**Gates que rechazan planos que tú mantendrías**")
        st.dataframe(
            pd.DataFrame(evaluation["gate_diagnostics"]),
            hide_index=True,
            width="stretch",
        )
    st.markdown("**Qué dimensión separa mejor tu criterio**")
    st.dataframe(
        pd.DataFrame(evaluation["dimension_separation"]),
        hide_index=True,
        width="stretch",
    )


# -------------------------------------------------------------------------- tab: audit


def tab_audit(
    document: dict[str, Any], result: dict[str, Any], config: dict[str, Any]
) -> None:
    st.subheader("Auditoría")
    columns = st.columns(2)
    with columns[0]:
        st.markdown("**Pipeline**")
        st.json(document["pipeline"], expanded=False)
        st.markdown("**Fuente**")
        st.json(document["source"], expanded=False)
    with columns[1]:
        st.markdown("**Artefactos**")
        st.json(document["artifacts"], expanded=False)
        st.markdown("**Resolución de análisis**")
        st.json(document["analysis_resolution"], expanded=False)

    st.divider()
    st.subheader("Config activa")
    st.caption(
        "Esta es exactamente la configuración que reproduce el ranking actual. "
        "Descárgala desde la barra lateral y pásala con `--config`."
    )
    st.json(config, expanded=False)

    st.divider()
    st.subheader("Catálogo de campos")
    st.caption(
        "Cada variable declara unidad, transformación, agregación y resolución de medida."
    )
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "variable": key,
                    "etiqueta": value["label_es"],
                    "unidad": value["unit_es"],
                    "agregación": value["aggregation"],
                    "medida en": value["measured_on"],
                    "descripción": value["description_es"],
                }
                for key, value in document["field_catalog"].items()
            ]
        ),
        hide_index=True,
        width="stretch",
    )

    st.divider()
    st.subheader("Normalización aplicada")
    normalization_rows = []
    for entry in result["normalization"].values():
        for group in ("components", "fallback_components"):
            for component in entry[group].values():
                normalization_rows.append(
                    {
                        "dimensión": entry["label_es"],
                        "componente": component["label_es"],
                        "variable": component["metric"],
                        "modo": component["mode"],
                        "método": component["method"],
                        "mín": round(float(component["low"]), 5),
                        "máx": round(float(component["high"]), 5),
                        "origen": component["source"],
                        "calibración": component["calibration"],
                        "nota": component.get("fallback_reason", ""),
                    }
                )
    st.dataframe(pd.DataFrame(normalization_rows), hide_index=True, width="stretch")

    st.divider()
    audit_path = document["artifacts"].get("audit_json")
    if audit_path and Path(audit_path).exists():
        st.download_button(
            "Descargar audit.json",
            data=Path(audit_path).read_bytes(),
            file_name="audit.json",
            mime="application/json",
        )


main()
