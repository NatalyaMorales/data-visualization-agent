"""
Agente de Perfilado y Recomendación Visual
==========================================
Flujo:
  1. Sube CSV -> perfila columnas
  2. Prolog recomienda gráficos
  3. Usuario SELECCIONA cuáles quiere + edita títulos
  4. Se renderizan SOLO los gráficos seleccionados
  5. Exportar PDF
"""

import json
from io import BytesIO
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
import streamlit as st

# ─── Constantes ───────────────────────────────────────────────────────────────
API_URL = "http://localhost:8000"
PROCESSED_CSV = Path(__file__).parent / "backend" / "temp" / "df_procesado.csv"

ROLE_OPTIONS = [
    "continua", "discreta", "categorica", "temporal",
    "binaria", "booleana", "texto_libre", "identificador", "desconocida"
]
ROLE_LABELS = {
    "continua": "Continua", "discreta": "Discreta", "categorica": "Categórica",
    "temporal": "Temporal", "binaria": "Binaria", "booleana": "Booleana",
    "texto_libre": "Texto libre", "identificador": "Identificador", "desconocida": "Desconocida",
}
AUDIENCE_LABELS = {
    "no_tecnica": "No técnica", "tecnica": "Técnica", "ejecutiva": "Ejecutiva",
}
CHART_ICONS = {
    "histograma": "", "barras": "", "lineas": "", "dispersion": "",
    "boxplot": "", "kpi": "", "pastel": "", "tabla": "", "mapa_calor": "",
}

# ─── Config ───────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Agente de Perfilado Visual",
    page_icon="graph",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
[data-testid="stAppViewContainer"] {
    background: linear-gradient(135deg, #0f0c29, #302b63, #24243e);
    color: #e8e8f0;
}
[data-testid="stSidebar"] {
    background: rgba(15,12,41,0.85);
    backdrop-filter: blur(12px);
    border-right: 1px solid rgba(255,255,255,0.08);
}
[data-testid="stExpander"] {
    background: rgba(255,255,255,0.04);
    border: 1px solid rgba(255,255,255,0.10);
    border-radius: 12px;
}
[data-testid="stBaseButton-primary"] {
    background: linear-gradient(90deg,#7c3aed,#4f46e5) !important;
    border: none !important; color: white !important;
    border-radius: 8px !important; font-weight: 600 !important;
}
[data-testid="stMetric"] {
    background: rgba(255,255,255,0.05); border-radius: 10px;
    padding: 12px; border: 1px solid rgba(255,255,255,0.08);
}
hr { border-color: rgba(255,255,255,0.10) !important; }
::-webkit-scrollbar { width: 6px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: #7c3aed; border-radius: 4px; }
.selection-card {
    background: rgba(255,255,255,0.04);
    border: 1px solid rgba(255,255,255,0.12);
    border-radius: 12px; padding: 14px 16px; margin-bottom: 10px;
}
.selection-card:hover { border-color: #7c3aed; }
</style>
""", unsafe_allow_html=True)

PLOTLY_TEMPLATE = "plotly_dark"

# ─── Helpers ──────────────────────────────────────────────────────────────────
def normalize_role(role: str) -> str:
    return {"categórica": "categorica", "texto libre": "texto_libre"}.get(
        role.strip().lower(), role.strip().lower()
    )


def render_chart(df: pd.DataFrame, item: dict, key_suffix: str = ""):
    """Renderiza UN gráfico según el JSON de selección del usuario."""
    chart_type = item["tipo_canonico"]
    cols = item["columnas_lista"]
    title = item["titulo"]

    try:
        fig = None

        if chart_type == "histograma" and cols:
            series = pd.to_numeric(df[cols[0]], errors="coerce").dropna()
            fig = px.histogram(series, x=series, nbins=25, title=title,
                               template=PLOTLY_TEMPLATE, color_discrete_sequence=["#7c3aed"])
            fig.update_layout(xaxis_title=cols[0], yaxis_title="Frecuencia")

        elif chart_type == "barras" and cols:
            vc = df[cols[0]].astype(str).value_counts().head(15).reset_index()
            vc.columns = [cols[0], "Frecuencia"]
            fig = px.bar(vc, x=cols[0], y="Frecuencia", title=title,
                         template=PLOTLY_TEMPLATE, color="Frecuencia",
                         color_continuous_scale="Plasma")
            fig.update_layout(xaxis_tickangle=-40)

        elif chart_type == "lineas" and len(cols) >= 2:
            plot_df = df[[cols[0], cols[1]]].copy()
            plot_df[cols[0]] = pd.to_datetime(plot_df[cols[0]], errors="coerce", dayfirst=True)
            plot_df[cols[1]] = pd.to_numeric(plot_df[cols[1]], errors="coerce")
            plot_df = plot_df.dropna().sort_values(cols[0])
            fig = px.line(plot_df, x=cols[0], y=cols[1], title=title,
                          template=PLOTLY_TEMPLATE, color_discrete_sequence=["#a855f7"], markers=True)

        elif chart_type == "dispersion" and len(cols) >= 2:
            plot_df = df[[cols[0], cols[1]]].copy()
            plot_df[cols[0]] = pd.to_numeric(plot_df[cols[0]], errors="coerce")
            plot_df[cols[1]] = pd.to_numeric(plot_df[cols[1]], errors="coerce")
            plot_df = plot_df.dropna()
            fig = px.scatter(plot_df, x=cols[0], y=cols[1], title=title,
                             template=PLOTLY_TEMPLATE, opacity=0.75,
                             color_discrete_sequence=["#818cf8"], trendline="ols")

        elif chart_type == "boxplot" and cols:
            series = pd.to_numeric(df[cols[0]], errors="coerce").dropna()
            fig = px.box(series, y=series, title=title,
                         template=PLOTLY_TEMPLATE, color_discrete_sequence=["#c084fc"])
            fig.update_layout(yaxis_title=cols[0])

        elif chart_type == "kpi" and cols:
            val = pd.to_numeric(df[cols[0]], errors="coerce").mean()
            fig = go.Figure(go.Indicator(
                mode="number", value=round(float(val), 2) if not pd.isna(val) else 0,
                title={"text": title, "font": {"size": 20}},
                number={"font": {"size": 52, "color": "#a855f7"}},
            ))
            fig.update_layout(template=PLOTLY_TEMPLATE, height=260,
                              paper_bgcolor="rgba(0,0,0,0)")

        elif chart_type == "pastel" and cols:
            vc = df[cols[0]].astype(str).value_counts().head(6).reset_index()
            vc.columns = [cols[0], "count"]
            fig = px.pie(vc, names=cols[0], values="count", title=title,
                         template=PLOTLY_TEMPLATE,
                         color_discrete_sequence=px.colors.sequential.Plasma_r, hole=0.35)

        elif chart_type == "tabla" and cols:
            vc = df[cols[0]].astype(str).value_counts().head(10).reset_index()
            vc.columns = [cols[0], "Frecuencia"]
            st.markdown(f"**{title}**")
            st.dataframe(vc, use_container_width=True, hide_index=True)
            return

        elif chart_type == "mapa_calor" and len(cols) >= 2:
            ct = pd.crosstab(df[cols[0]], df[cols[1]])
            fig = px.imshow(ct, title=title, template=PLOTLY_TEMPLATE,
                            color_continuous_scale="Plasma", aspect="auto", text_auto=True)
        else:
            st.info(f"**{title}** — no se grafica directamente.")
            return

        if fig:
            fig.update_layout(
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                font_color="#e8e8f0", margin=dict(t=50, b=30, l=20, r=20),
            )
            st.plotly_chart(fig, use_container_width=True, key=f"chart_{key_suffix}")

    except Exception as exc:
        st.warning(f"No se pudo renderizar **{title}**: {exc}")


# ─── Sidebar ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## Configuración")
    st.markdown("---")
    audience = st.selectbox("Audiencia objetivo", list(AUDIENCE_LABELS.keys()),
                            format_func=lambda x: AUDIENCE_LABELS[x])
    st.markdown("**Formato del CSV**")
    separator = st.selectbox("Separador", [",", ";", "\t"],
                             format_func=lambda x: {",": "Coma (,)", ";": "Punto y coma (;)", "\t": "Tab"}[x])
    encoding = st.selectbox("Encoding", ["utf-8", "latin-1", "cp1252"])
    st.markdown("**Tratamiento de nulos**")
    null_threshold = st.slider("Umbral de nulos (%)", 0, 100, 40)
    remove_cols = st.checkbox("Eliminar columnas con muchos nulos", value=False)
    skip_nulls = st.checkbox("Omitir tratamiento", value=True)
    null_strategy = st.selectbox(
        "Estrategia", ["eliminar_filas", "imputar"],
        format_func=lambda x: "Eliminar filas con nulos" if x == "eliminar_filas" else "Imputar media / moda",
        disabled=skip_nulls,
    )
    st.markdown("---")
    try:
        h = requests.get(f"{API_URL}/api/health", timeout=2)
        prolog_ok = h.json().get("prolog_disponible", False)
        st.success("API conectada")
        if not prolog_ok:
            st.warning("Prolog no disponible\n(instala SWI-Prolog)")
    except Exception:
        st.error("API no responde\n`uvicorn main:app --reload`")

# ─── Cabecera ─────────────────────────────────────────────────────────────────
st.markdown("""
<div style="text-align:center; padding:2rem 0 1rem 0;">
  <h1 style="font-size:2.4rem; font-weight:800;
             background:linear-gradient(90deg,#a855f7,#818cf8);
             -webkit-background-clip:text; -webkit-text-fill-color:transparent;">
    Agente de Perfilado Visual
  </h1>
  <p style="color:#94a3b8; font-size:1.05rem;">
    Sube un CSV → Prolog infiere visualizaciones → <b>tú eliges cuáles renderizar</b>
  </p>
</div>
""", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# PASO 1: Carga CSV
# ══════════════════════════════════════════════════════════════════════════════
uploaded = st.file_uploader("Sube tu archivo CSV", type=["csv"],
                            help="El agente perfilará las columnas y consultará las reglas Prolog.")
if uploaded is None:
    st.info("Sube un CSV para comenzar.")
    st.stop()

# ══════════════════════════════════════════════════════════════════════════════
# PASO 2: Perfilar
# ══════════════════════════════════════════════════════════════════════════════
if "profile_data" not in st.session_state or st.session_state.get("last_file") != uploaded.name:
    with st.spinner("Perfilando dataset..."):
        try:
            resp = requests.post(
                f"{API_URL}/api/profile",
                files={"file": (uploaded.name, uploaded.getvalue(), "text/csv")},
                data={"separator": separator, "encoding": encoding},
                timeout=30,
            )
            resp.raise_for_status()
            st.session_state["profile_data"] = resp.json()
            st.session_state["last_file"] = uploaded.name
            st.session_state.pop("recs", None)
            st.session_state.pop("selected_charts", None)
        except Exception as exc:
            st.error(f"Error al perfilar: {exc}")
            st.stop()

profile_data = st.session_state["profile_data"]

c1, c2, c3, c4 = st.columns(4)
c1.metric("Filas", f"{profile_data['rows']:,}")
c2.metric("Columnas", f"{profile_data['columns']}")
num_num = sum(1 for c in profile_data["profile"] if c["rol_sugerido"] in ("continua", "discreta", "binaria"))
num_cat = sum(1 for c in profile_data["profile"] if c["rol_sugerido"] in ("categorica", "booleana"))
c3.metric("Numéricas", num_num)
c4.metric("Categóricas", num_cat)

# ══════════════════════════════════════════════════════════════════════════════
# PASO 3: Ajuste de roles
# ══════════════════════════════════════════════════════════════════════════════
with st.expander("Perfil de columnas y ajuste de roles", expanded=False):
    df_profile = pd.DataFrame(profile_data["profile"])
    st.dataframe(
        df_profile.rename(columns={
            "columna": "Columna", "dtype_original": "Tipo original",
            "nulos_porcentaje": "Nulos %", "unicos": "Únicos",
            "muestra": "Muestra", "rol_sugerido": "Rol sugerido",
        }),
        use_container_width=True, hide_index=True,
    )
    st.markdown("**Ajusta los roles si el agente los infirió incorrectamente:**")

    n_cols_ui = 4
    col_chunks = [profile_data["profile"][i:i+n_cols_ui]
                  for i in range(0, len(profile_data["profile"]), n_cols_ui)]
    for chunk in col_chunks:
        ui_cols = st.columns(n_cols_ui)
        for idx, col_info in enumerate(chunk):
            col_name = col_info["columna"]
            suggested = normalize_role(col_info.get("rol_sugerido", "continua"))
            if suggested not in ROLE_OPTIONS:
                suggested = "continua"
            with ui_cols[idx]:
                st.selectbox(col_name, ROLE_OPTIONS,
                             index=ROLE_OPTIONS.index(suggested),
                             format_func=lambda x: ROLE_LABELS[x],
                             key=f"role_{col_name}")

# Recoger roles desde session_state (funciona tanto si el expander está abierto o cerrado)
approved_roles: dict = {}
for col_info in profile_data["profile"]:
    col_name = col_info["columna"]
    suggested = normalize_role(col_info.get("rol_sugerido", "continua"))
    if suggested not in ROLE_OPTIONS:
        suggested = "continua"
    approved_roles[col_name] = st.session_state.get(f"role_{col_name}", suggested)

# ══════════════════════════════════════════════════════════════════════════════
# PASO 4: Generar recomendaciones Prolog
# ══════════════════════════════════════════════════════════════════════════════
st.markdown("---")
gen_btn = st.button("Generar Recomendaciones con Prolog",
                    type="primary", use_container_width=True)

if gen_btn:
    uploaded.seek(0)
    with st.spinner("Consultando motor de inferencia Prolog..."):
        try:
            resp2 = requests.post(
                f"{API_URL}/api/process",
                files={"file": (uploaded.name, uploaded.getvalue(), "text/csv")},
                data={
                    "separator": separator, "encoding": encoding,
                    "null_threshold": null_threshold,
                    "remove_high_null_cols": str(remove_cols).lower(),
                    "skip_null_removal": str(skip_nulls).lower(),
                    "null_strategy": null_strategy,
                    "audience": audience,
                    "approved_roles_json": json.dumps(approved_roles),
                },
                timeout=60,
            )
            resp2.raise_for_status()
            result = resp2.json()
            if "error" in result:
                st.error(result["error"])
                st.stop()
            st.session_state["recs"] = result["recommendations"]
            st.session_state["rows_processed"] = result["rows_processed"]
            st.session_state["cols_processed"] = result["columns_processed"]
            st.session_state.pop("selected_charts", None)  # resetear selección previa
            st.success(f"**{len(result['recommendations'])} recomendaciones** generadas.")
        except Exception as exc:
            st.error(f"Error procesando: {exc}")
            st.stop()

if "recs" not in st.session_state:
    st.stop()

recs: list[dict] = st.session_state["recs"]
graficables = [r for r in recs if r.get("es_grafico")]
no_graficables = [r for r in recs if not r.get("es_grafico")]

# ══════════════════════════════════════════════════════════════════════════════
# PASO 5 SELECCIÓN DE GRÁFICOS — produce el JSON de salida
# ══════════════════════════════════════════════════════════════════════════════
st.markdown("---")
st.markdown("""
<h2 style="background:linear-gradient(90deg,#a855f7,#818cf8);
           -webkit-background-clip:text;-webkit-text-fill-color:transparent;
           font-size:1.6rem; font-weight:800;">
  Selecciona los gráficos que quieres visualizar
</h2>
<p style="color:#94a3b8; margin-top:-8px;">
  Marca los gráficos recomendados, edita el título si lo deseas,
  y presiona <b>"Renderizar seleccionados"</b>.
</p>
""", unsafe_allow_html=True)

# Filtros de búsqueda
all_types = sorted({r["tipo_grafico"] for r in graficables})
all_cols = sorted({col for r in graficables for col in (r.get("columnas_lista") or [])})

fcol1, fcol2 = st.columns([1, 1])
with fcol1:
    sel_types = st.multiselect(
        "Filtrar por tipo de gráfico",
        all_types,
        default=all_types,
        placeholder="Todos los tipos",
    )
with fcol2:
    sel_cols = st.multiselect(
        "Filtrar por columna",
        all_cols,
        default=[],
        placeholder="Todas las columnas",
    )

filtered_recs = [
    r for r in graficables
    if r["tipo_grafico"] in sel_types
    and (not sel_cols or any(c in sel_cols for c in (r.get("columnas_lista") or [])))
]

if not filtered_recs:
    st.warning("No hay recomendaciones que coincidan con los filtros seleccionados.")
    st.stop()

sel_all = st.checkbox("Seleccionar / deseleccionar todos los filtrados", value=False, key="sel_all_toggle")

selection_inputs = []  # [{tipo_canonico, columnas_lista, titulo, justificacion}]

for i, rec in enumerate(filtered_recs):
    icon = CHART_ICONS.get(rec.get("tipo_canonico", ""), "")
    default_title = f"{rec['tipo_grafico']} — {rec.get('columnas', '')}"
    default_checked = sel_all

    col_check, col_info, col_title = st.columns([0.08, 0.42, 0.50])

    with col_check:
        checked = st.checkbox("", value=default_checked, key=f"sel_{i}",
                              label_visibility="collapsed")
    with col_info:
        st.markdown(
            f"<div style='padding:6px 0;'>"
            f"<span style='font-size:1.1rem;'>{icon} <b>{rec['tipo_grafico']}</b></span><br>"
            f"<span style='color:#94a3b8; font-size:0.85rem;'>Columnas: <code>{rec.get('columnas','')}</code></span><br>"
            f"<span style='color:#64748b; font-size:0.78rem;'>{rec.get('justificacion','')}</span>"
            f"</div>",
            unsafe_allow_html=True,
        )
    with col_title:
        title_input = st.text_input("Título", value=default_title,
                                    key=f"title_{i}", label_visibility="collapsed",
                                    placeholder="Título del gráfico...")

    if checked:
        selection_inputs.append({
            "tipo_canonico": rec.get("tipo_canonico", ""),
            "columnas_lista": rec.get("columnas_lista", []),
            "titulo": title_input,
            "justificacion": rec.get("justificacion", ""),
            "tipo_grafico": rec.get("tipo_grafico", ""),
        })

# JSON de salida visible
if selection_inputs:
    st.markdown(f"**{len(selection_inputs)} gráfico(s) seleccionado(s)**")
    with st.expander("Ver JSON de selección (para depuración / exportar)", expanded=False):
        st.json(selection_inputs)
else:
    st.info("Marca al menos un gráfico para continuar.")

render_btn = st.button(
    f"Renderizar {len(selection_inputs)} gráfico(s) seleccionado(s)",
    type="primary", use_container_width=True,
    disabled=len(selection_inputs) == 0,
)

if render_btn:
    st.session_state["selected_charts"] = selection_inputs

# ══════════════════════════════════════════════════════════════════════════════
# PASO 6: Renderizar SOLO los gráficos seleccionados
# ══════════════════════════════════════════════════════════════════════════════
if "selected_charts" not in st.session_state or not st.session_state["selected_charts"]:
    # Mostrar columnas sin gráfico
    if no_graficables:
        with st.expander(f"Columnas sin gráfico directo ({len(no_graficables)})"):
            for r in no_graficables:
                st.markdown(f"- **{r.get('columnas','')}** — {r.get('justificacion','')}")
    st.stop()

selected_charts: list[dict] = st.session_state["selected_charts"]

if not PROCESSED_CSV.exists():
    st.error(f"No se encontró el CSV procesado en `{PROCESSED_CSV}`.")
    st.stop()

df_proc = pd.read_csv(PROCESSED_CSV)

st.markdown("---")
st.markdown(f"""
<h2 style="background:linear-gradient(90deg,#a855f7,#818cf8);
           -webkit-background-clip:text;-webkit-text-fill-color:transparent;
           font-size:1.8rem; font-weight:800;">
  Dashboard — {len(selected_charts)} visualizacion(es)
</h2>
""", unsafe_allow_html=True)

for i in range(0, len(selected_charts), 2):
    pair = selected_charts[i:i+2]
    grid_cols = st.columns(len(pair))
    for j, item in enumerate(pair):
        with grid_cols[j]:
            with st.container(border=True):
                st.markdown(f"**{item['titulo']}**")
                st.caption(f"{item.get('justificacion','')}")
                render_chart(df_proc, item, key_suffix=f"{i}_{j}")

# Columnas sin gráfico
if no_graficables:
    with st.expander(f"Columnas sin gráfico directo ({len(no_graficables)})"):
        for r in no_graficables:
            st.markdown(f"- **{r.get('columnas','')}** — {r.get('justificacion','')}")

# ══════════════════════════════════════════════════════════════════════════════
# PASO 7: Exportar PDF (solo los seleccionados)
# ══════════════════════════════════════════════════════════════════════════════
st.markdown("---")
st.subheader("Exportar Reporte PDF")
st.caption(f"Se incluirán {len(selected_charts)} gráfica(s) seleccionada(s).")

if st.button("Generar y descargar PDF", use_container_width=True):
    # Mapear selected_charts al formato que espera /api/report
    recs_for_pdf = [
        {
            "tipo_grafico": item["tipo_grafico"],
            "tipo_canonico": item["tipo_canonico"],
            "columnas": ", ".join(item["columnas_lista"]),
            "columnas_lista": item["columnas_lista"],
            "justificacion": item["justificacion"],
            "es_grafico": True,
        }
        for item in selected_charts
    ]
    with st.spinner("Generando reporte PDF..."):
        try:
            resp_pdf = requests.post(
                f"{API_URL}/api/report",
                json={"recommendations": recs_for_pdf},
                timeout=120,
            )
            resp_pdf.raise_for_status()
            st.download_button(
                label="Descargar reporte_visualizaciones.pdf",
                data=resp_pdf.content,
                file_name="reporte_visualizaciones.pdf",
                mime="application/pdf",
                use_container_width=True,
            )
        except Exception as exc:
            st.error(f"No se pudo generar el PDF: {exc}")
