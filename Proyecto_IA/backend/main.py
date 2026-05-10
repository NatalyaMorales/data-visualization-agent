from io import StringIO, BytesIO
from pathlib import Path
from typing import Dict, List, Optional
import json
import re
import textwrap

import numpy as np
import pandas as pd
from fastapi import FastAPI, File, Form, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages

# Prolog
try:
    from pyswip import Prolog
    PROLOG_AVAILABLE = True
except Exception:
    PROLOG_AVAILABLE = False


app = FastAPI(title="Agente de Perfilado y Recomendación Visual")

# Rutas
BASE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BASE_DIR.parent

FRONTEND_CANDIDATES = [
    PROJECT_DIR / "frontend",      # Proyecto_IA/frontend
    BASE_DIR / "frontend",         # Proyecto_IA/backend/frontend
]

FRONTEND_DIR = None
for candidate in FRONTEND_CANDIDATES:
    if candidate.exists() and candidate.is_dir():
        FRONTEND_DIR = candidate
        break

if FRONTEND_DIR is None:
    raise FileNotFoundError(
        "No se encontró la carpeta frontend. "
        f"Rutas revisadas: {[str(p) for p in FRONTEND_CANDIDATES]}"
    )

PROLOG_DIR = BASE_DIR / "prolog"
PROLOG_DIR.mkdir(exist_ok=True)

TEMP_DIR = BASE_DIR / "temp"
TEMP_DIR.mkdir(exist_ok=True)

FACTS_FILE = PROLOG_DIR / "hechos_dataset.pl"
RULES_FILE = PROLOG_DIR / "reglas.pl"
PROCESSED_DATA_FILE = TEMP_DIR / "df_procesado.csv"
RECOMMENDATIONS_FILE = TEMP_DIR / "recomendaciones.json"

if not FRONTEND_DIR.exists():
    raise FileNotFoundError(f"No se encontró la carpeta frontend en: {FRONTEND_DIR}")

app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


@app.get("/")
def serve_frontend():
    return FileResponse(FRONTEND_DIR / "index.html")


# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Modelos para reporte
class RecommendationSelection(BaseModel):
    id: Optional[int] = None   # opcional: Prolog no genera id
    tipo_grafico: str
    tipo_canonico: Optional[str] = None
    columnas: Optional[str] = None
    columnas_lista: List[str] = []
    justificacion: str = ""
    es_grafico: bool = True


class ReportRequest(BaseModel):
    recommendations: List[RecommendationSelection]


# Utilidades de perfilado
def sanitize_name(name: str) -> str:
    name = str(name).strip().lower()
    name = re.sub(r"[^\w\s]", "_", name, flags=re.UNICODE)
    name = re.sub(r"\s+", "_", name)
    name = re.sub(r"_+", "_", name)
    name = name.strip("_")
    if not name:
        name = "columna_sin_nombre"
    if name[0].isdigit():
        name = f"col_{name}"
    return name


def escape_prolog_string(value: str) -> str:
    return str(value).replace("\\", "\\\\").replace("'", "\\'")


def detect_datetime(series: pd.Series, threshold: float = 0.80) -> bool:
    s = series.dropna()
    if s.empty:
        return False

    if pd.api.types.is_datetime64_any_dtype(series):
        return True

    if pd.api.types.is_numeric_dtype(series):
        return False

    try:
        parsed = pd.to_datetime(s.astype(str), errors="coerce", dayfirst=True)
        success_ratio = parsed.notna().mean()
        return success_ratio >= threshold
    except Exception:
        return False


def infer_column_type(
    series: pd.Series,
    categorical_ratio_threshold: float = 0.05,
    categorical_unique_limit: int = 30,
    datetime_parse_threshold: float = 0.80
) -> str:
    s = series.dropna()

    if s.empty:
        return "desconocida"

    if pd.api.types.is_bool_dtype(series):
        return "booleana"

    if detect_datetime(series, threshold=datetime_parse_threshold):
        return "temporal"

    if pd.api.types.is_numeric_dtype(series):
        unique_count = s.nunique(dropna=True)
        total_count = len(s)
        unique_ratio = unique_count / total_count if total_count > 0 else 1.0

        if unique_count == 2:
            return "binaria"

        if unique_count <= 10:
            return "discreta"

        if unique_ratio < categorical_ratio_threshold:
            return "discreta"

        return "continua"

    unique_count = s.astype(str).nunique(dropna=True)

    if unique_count == 2:
        return "binaria"

    if unique_count <= categorical_unique_limit:
        return "categorica"

    return "texto_libre"


def get_column_summary(series: pd.Series, inferred_type: str) -> dict:
    s = series.dropna()

    summary = {
        "original_name": str(series.name),
        "safe_name": sanitize_name(series.name),
        "inferred_type": inferred_type,
        "n_total": int(len(series)),
        "n_non_null": int(series.notna().sum()),
        "n_null": int(series.isna().sum()),
        "null_ratio": float(series.isna().mean()),
        "n_unique": int(s.nunique(dropna=True)) if not s.empty else 0,
    }

    if inferred_type in {"continua", "discreta", "binaria"}:
        numeric_s = pd.to_numeric(s, errors="coerce").dropna()
        if not numeric_s.empty:
            summary.update({
                "min": float(numeric_s.min()),
                "max": float(numeric_s.max()),
                "mean": float(numeric_s.mean()),
                "std": float(numeric_s.std(ddof=0)) if len(numeric_s) > 1 else 0.0,
            })

    elif inferred_type == "temporal":
        parsed = pd.to_datetime(s, errors="coerce", dayfirst=True).dropna()
        if not parsed.empty:
            summary.update({
                "min_date": str(parsed.min()),
                "max_date": str(parsed.max()),
            })

    elif inferred_type in {"categorica", "texto_libre"}:
        value_counts = s.astype(str).value_counts(dropna=True)
        summary.update({
            "top_categories": value_counts.head(10).to_dict()
        })

    return summary


def profile_dataframe(df: pd.DataFrame) -> dict:
    dataset_info = {
        "n_rows": int(len(df)),
        "n_columns": int(len(df.columns)),
        "columns": []
    }

    for col in df.columns:
        inferred_type = infer_column_type(df[col])
        summary = get_column_summary(df[col], inferred_type)
        dataset_info["columns"].append(summary)

    return dataset_info


def build_profile_for_front(df: pd.DataFrame) -> List[Dict]:
    result = []
    prof = profile_dataframe(df)

    role_map = {
        "categorica": "categórica"
    }

    for col in prof["columns"]:
        inferred = col["inferred_type"]
        inferred_front = role_map.get(inferred, inferred)

        result.append({
            "columna": col["original_name"],
            "dtype_original": str(df[col["original_name"]].dtype),
            "nulos_porcentaje": round(col["null_ratio"] * 100, 2),
            "unicos": col["n_unique"],
            "muestra": df[col["original_name"]].dropna().astype(str).head(3).tolist(),
            "rol_sugerido": inferred_front
        })

    return result



# Conversión front -> Prolog

def normalize_front_role_to_prolog(role: str) -> str:
    mapping = {
        "categórica": "categorica",
        "categorica": "categorica",
        "continua": "continua",
        "discreta": "discreta",
        "texto libre": "texto_libre",
        "texto_libre": "texto_libre",
        "temporal": "temporal",
        "binaria": "binaria",
        "booleana": "booleana",
        "identificador": "identificador",
        "desconocida": "desconocida",
    }
    return mapping.get(role, sanitize_name(role))


def build_profile_with_approved_roles(df: pd.DataFrame, approved_roles: Dict[str, str]) -> dict:
    dataset_info = {
        "n_rows": int(len(df)),
        "n_columns": int(len(df.columns)),
        "columns": []
    }

    for col in df.columns:
        approved_role = approved_roles.get(col)
        if approved_role:
            inferred_type = normalize_front_role_to_prolog(approved_role)
        else:
            inferred_type = infer_column_type(df[col])

        summary = get_column_summary(df[col], inferred_type)
        dataset_info["columns"].append(summary)

    return dataset_info


def profile_to_prolog_facts(profile: dict, audience: str) -> str:
    lines = []

    lines.append("% ===== Hechos del dataset =====")
    lines.append(f"dataset_filas({profile['n_rows']}).")
    lines.append(f"dataset_columnas({profile['n_columns']}).")
    lines.append("")

    audience_atom = sanitize_name(audience)
    lines.append(f"audiencia({audience_atom}).")
    lines.append("")

    for col in profile["columns"]:
        safe_name = col["safe_name"]
        original_name = escape_prolog_string(col["original_name"])
        inferred_type = sanitize_name(col["inferred_type"])

        lines.append(f"columna({safe_name}).")
        lines.append(f"nombre_original({safe_name}, '{original_name}').")
        lines.append(f"tipo_columna({safe_name}, {inferred_type}).")
        lines.append(f"nulos({safe_name}, {col['n_null']}).")
        lines.append(f"proporcion_nulos({safe_name}, {col['null_ratio']:.6f}).")
        lines.append(f"valores_unicos({safe_name}, {col['n_unique']}).")

        if inferred_type in {"continua", "discreta", "binaria"}:
            if "min" in col and "max" in col:
                lines.append(f"rango({safe_name}, {col['min']}, {col['max']}).")
                lines.append(f"media({safe_name}, {col['mean']}).")
                lines.append(f"desviacion({safe_name}, {col['std']}).")

        elif inferred_type == "temporal":
            if "min_date" in col and "max_date" in col:
                min_date = escape_prolog_string(col["min_date"])
                max_date = escape_prolog_string(col["max_date"])
                lines.append(f"rango_fecha({safe_name}, '{min_date}', '{max_date}').")

        elif inferred_type in {"categorica", "texto_libre"}:
            lines.append(f"num_categorias({safe_name}, {col['n_unique']}).")

        lines.append("")

    return "\n".join(lines)


def save_prolog_facts(profile: dict, audience: str, output_path: Path):
    facts = profile_to_prolog_facts(profile, audience)
    output_path.write_text(facts, encoding="utf-8")



# Limpieza / procesamiento

def convert_series_by_role(series: pd.Series, role: str) -> pd.Series:
    role = normalize_front_role_to_prolog(role)

    if role == "temporal":
        return pd.to_datetime(series, errors="coerce", dayfirst=True)

    if role in {"continua", "discreta", "binaria"}:
        return pd.to_numeric(series, errors="coerce")

    return series.astype("string")


def process_dataframe(
    df: pd.DataFrame,
    approved_roles: Dict[str, str],
    null_threshold: float,
    remove_high_null_cols: bool,
    skip_null_removal: bool,
    null_strategy: str
) -> pd.DataFrame:
    df_processed = df.copy()

    for col, role in approved_roles.items():
        if col in df_processed.columns:
            df_processed[col] = convert_series_by_role(df_processed[col], role)

    if remove_high_null_cols:
        cols_to_remove = [
            col for col in df_processed.columns
            if df_processed[col].isna().mean() * 100 >= null_threshold
        ]
        df_processed = df_processed.drop(columns=cols_to_remove, errors="ignore")

    if not skip_null_removal:
        if null_strategy == "eliminar_filas":
            df_processed = df_processed.dropna()
        elif null_strategy == "imputar":
            for col in df_processed.columns:
                if df_processed[col].isna().sum() > 0:
                    if pd.api.types.is_numeric_dtype(df_processed[col]):
                        df_processed[col] = df_processed[col].fillna(df_processed[col].mean())
                    else:
                        mode_series = df_processed[col].mode(dropna=True)
                        if not mode_series.empty:
                            df_processed[col] = df_processed[col].fillna(mode_series.iloc[0])

    return df_processed



# Prolog: recomendaciones

def safe_to_original_map(profile: dict) -> Dict[str, str]:
    return {
        col["safe_name"]: col["original_name"]
        for col in profile["columns"]
    }


def parse_prolog_columns(raw_columns: str) -> List[str]:
    text = str(raw_columns).strip()
    if not text:
        return []

    if text.startswith("par(") and text.endswith(")"):
        inside = text[4:-1]
        return [part.strip() for part in inside.split(",") if part.strip()]

    return [text]


def canonical_chart_type(prolog_type: str) -> str:
    mapping = {
        "histograma": "histograma",
        "barras": "barras",
        "lineas": "lineas",
        "dispersion": "dispersion",
        "boxplot": "boxplot",
        "kpi": "kpi",
        "pastel": "pastel",
        "tabla": "tabla",
        "mapa_calor": "mapa_calor",
        "no_graficar_directamente": "no_graficar_directamente",
    }
    return mapping.get(str(prolog_type).strip().lower(), sanitize_name(prolog_type))


def chart_label(chart_type: str) -> str:
    mapping = {
        "histograma": "Histograma",
        "barras": "Barras",
        "lineas": "Líneas",
        "dispersion": "Dispersión",
        "boxplot": "Boxplot",
        "kpi": "Tarjeta (KPI)",
        "pastel": "Gráfico de Pastel",
        "tabla": "Tabla de Datos",
        "mapa_calor": "Mapa de Calor",
        "no_graficar_directamente": "No graficar directamente",
    }
    return mapping.get(chart_type, chart_type.replace("_", " ").title())


def query_prolog_recommendations(profile: dict) -> List[Dict]:
    if not PROLOG_AVAILABLE:
        raise RuntimeError(
            "No se pudo usar Prolog desde Python. Instala SWI-Prolog y pyswip."
        )

    name_map = safe_to_original_map(profile)

    prolog = Prolog()
    prolog.consult(str(RULES_FILE))
    prolog.consult(str(FACTS_FILE))

    query = """
        recomendacion(Tipo, Columnas, Justificacion)
    """

    results = []
    for sol in prolog.query(query):
        tipo_raw = str(sol["Tipo"]).strip()
        tipo_canonico = canonical_chart_type(tipo_raw)

        columnas_raw = str(sol["Columnas"]).strip()
        columnas_safe = parse_prolog_columns(columnas_raw)
        columnas_originales = [name_map.get(col, col) for col in columnas_safe]

        results.append({
            "tipo_grafico": chart_label(tipo_canonico),
            "tipo_canonico": tipo_canonico,
            "columnas": ", ".join(columnas_originales),
            "columnas_lista": columnas_originales,
            "justificacion": str(sol["Justificacion"]),
            "es_grafico": tipo_canonico != "no_graficar_directamente",
        })

    unique = []
    seen = set()
    for r in results:
        key = (
            r["tipo_grafico"],
            tuple(r["columnas_lista"]),
            r["justificacion"],
            r["es_grafico"],
        )
        if key not in seen:
            seen.add(key)
            unique.append(r)

    return unique



# Utilidades para reporte

def save_processed_dataframe(df: pd.DataFrame):
    df.to_csv(PROCESSED_DATA_FILE, index=False, encoding="utf-8-sig")


def load_processed_dataframe() -> pd.DataFrame:
    if not PROCESSED_DATA_FILE.exists():
        raise HTTPException(
            status_code=400,
            detail="No hay un dataset procesado disponible. Primero genera recomendaciones."
        )
    return pd.read_csv(PROCESSED_DATA_FILE)


def save_recommendations_cache(recommendations: List[Dict]):
    RECOMMENDATIONS_FILE.write_text(
        json.dumps(recommendations, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )


def wrap_text(text: str, width: int = 90) -> str:
    return "\n".join(textwrap.wrap(str(text), width=width))


def ensure_columns_exist(df: pd.DataFrame, columns: List[str]):
    missing = [col for col in columns if col not in df.columns]
    if missing:
        raise ValueError(f"No se encontraron las columnas necesarias: {', '.join(missing)}")


def build_chart_figure(df: pd.DataFrame, recommendation: RecommendationSelection):
    chart_type = (recommendation.tipo_canonico or "").strip().lower()
    columns = recommendation.columnas_lista or []

    if chart_type == "no_graficar_directamente":
        raise ValueError("Esta recomendación no corresponde a un gráfico directo.")

    fig, ax = plt.subplots(figsize=(11, 6.5))

    try:
        if chart_type == "histograma":
            ensure_columns_exist(df, columns[:1])
            col = columns[0]
            series = pd.to_numeric(df[col], errors="coerce").dropna()
            if series.empty:
                raise ValueError(f"La columna '{col}' no tiene datos numéricos válidos para histograma.")
            ax.hist(series, bins=15, edgecolor="black")
            ax.set_title(f"Histograma de {col}", fontsize=16, pad=12)
            ax.set_xlabel(col)
            ax.set_ylabel("Frecuencia")
            ax.grid(axis="y", alpha=0.25)

        elif chart_type == "barras":
            ensure_columns_exist(df, columns[:1])
            col = columns[0]
            counts = df[col].astype(str).fillna("NA").value_counts().head(15)
            ax.bar(counts.index, counts.values)
            ax.set_title(f"Barras de {col}", fontsize=16, pad=12)
            ax.set_xlabel(col)
            ax.set_ylabel("Frecuencia")
            ax.tick_params(axis="x", rotation=45)
            ax.grid(axis="y", alpha=0.25)

        elif chart_type == "lineas":
            ensure_columns_exist(df, columns[:2])
            x_col, y_col = columns[0], columns[1]
            plot_df = df[[x_col, y_col]].copy()
            plot_df[x_col] = pd.to_datetime(plot_df[x_col], errors="coerce", dayfirst=True)
            plot_df[y_col] = pd.to_numeric(plot_df[y_col], errors="coerce")
            plot_df = plot_df.dropna().sort_values(x_col)
            if plot_df.empty:
                raise ValueError(f"No hay datos válidos para la serie temporal {x_col} / {y_col}.")
            ax.plot(plot_df[x_col], plot_df[y_col], marker="o")
            ax.set_title(f"Líneas de {y_col} por {x_col}", fontsize=16, pad=12)
            ax.set_xlabel(x_col)
            ax.set_ylabel(y_col)
            ax.tick_params(axis="x", rotation=45)
            ax.grid(alpha=0.25)

        elif chart_type == "dispersion":
            ensure_columns_exist(df, columns[:2])
            x_col, y_col = columns[0], columns[1]
            plot_df = df[[x_col, y_col]].copy()
            plot_df[x_col] = pd.to_numeric(plot_df[x_col], errors="coerce")
            plot_df[y_col] = pd.to_numeric(plot_df[y_col], errors="coerce")
            plot_df = plot_df.dropna()
            if plot_df.empty:
                raise ValueError(f"No hay datos válidos para la dispersión entre {x_col} y {y_col}.")
            ax.scatter(plot_df[x_col], plot_df[y_col], alpha=0.8)
            ax.set_title(f"Dispersión de {x_col} vs {y_col}", fontsize=16, pad=12)
            ax.set_xlabel(x_col)
            ax.set_ylabel(y_col)
            ax.grid(alpha=0.25)

        elif chart_type == "boxplot":
            ensure_columns_exist(df, columns[:1])
            col = columns[0]
            series = pd.to_numeric(df[col], errors="coerce").dropna()
            if series.empty:
                raise ValueError(f"La columna '{col}' no tiene datos numéricos válidos para boxplot.")
            ax.boxplot(series)
            ax.set_title(f"Boxplot de {col}", fontsize=16, pad=12)
            ax.set_xticklabels([col])
            ax.grid(axis="y", alpha=0.25)

        elif chart_type == "kpi":
            ensure_columns_exist(df, columns[:1])
            col = columns[0]
            val = pd.to_numeric(df[col], errors="coerce").mean()
            ax.axis('off')
            ax.text(0.5, 0.6, f"Promedio de {col}", ha='center', va='center', fontsize=20)
            ax.text(0.5, 0.4, f"{val:.2f}", ha='center', va='center', fontsize=40, fontweight='bold')
            ax.set_title(f"KPI: {col}", fontsize=16, pad=12)

        elif chart_type == "pastel":
            ensure_columns_exist(df, columns[:1])
            col = columns[0]
            counts = df[col].astype(str).fillna("NA").value_counts().head(5)
            if counts.empty:
                raise ValueError("No hay datos para pastel")
            ax.pie(counts.values, labels=counts.index, autopct='%1.1f%%', startangle=90)
            ax.set_title(f"Proporciones de {col}", fontsize=16, pad=12)

        elif chart_type == "tabla":
            ensure_columns_exist(df, columns[:1])
            col = columns[0]
            counts = df[col].astype(str).fillna("NA").value_counts().head(10).reset_index()
            counts.columns = [col, 'Frecuencia']
            ax.axis('off')
            table = ax.table(cellText=counts.values, colLabels=counts.columns, loc='center', cellLoc='center')
            table.scale(1, 1.5)
            table.auto_set_font_size(False)
            table.set_fontsize(12)
            ax.set_title(f"Top 10 Categorías de {col}", fontsize=16, pad=12)
            
        elif chart_type == "mapa_calor":
            ensure_columns_exist(df, columns[:2])
            x_col, y_col = columns[0], columns[1]
            crosstab = pd.crosstab(df[x_col], df[y_col])
            cax = ax.matshow(crosstab, cmap='Blues')
            fig.colorbar(cax)
            ax.set_xticks(range(len(crosstab.columns)))
            ax.set_yticks(range(len(crosstab.index)))
            ax.set_xticklabels(crosstab.columns, rotation=45)
            ax.set_yticklabels(crosstab.index)
            ax.set_title(f"Mapa de Calor: {x_col} vs {y_col}", fontsize=16, pad=20)

        else:
            raise ValueError(f"Tipo de gráfico no soportado: {chart_type}")

        fig.tight_layout()
        return fig

    except Exception:
        plt.close(fig)
        raise


def build_intro_page(pdf: PdfPages, total_graphs: int):
    fig, ax = plt.subplots(figsize=(11, 8.5))
    ax.axis("off")
    ax.text(
        0.5, 0.78,
        "Reporte de Visualizaciones",
        ha="center", va="center",
        fontsize=24,
        fontweight="bold"
    )
    ax.text(
        0.5, 0.66,
        "Generado automáticamente a partir de las visualizaciones seleccionadas",
        ha="center", va="center",
        fontsize=12
    )
    ax.text(
        0.5, 0.58,
        f"Total de gráficas incluidas: {total_graphs}",
        ha="center", va="center",
        fontsize=13
    )
    ax.text(
        0.08, 0.38,
        wrap_text(
            "Este reporte reúne las visualizaciones elegidas en la interfaz. "
            "Cada gráfica fue construida en Python con base en el dataset procesado "
            "y en las reglas de recomendación definidas para el agente."
        ),
        fontsize=12
    )
    pdf.savefig(fig, bbox_inches="tight")
    plt.close(fig)


def build_description_page(pdf: PdfPages, recommendation: RecommendationSelection):
    fig, ax = plt.subplots(figsize=(11, 8.5))
    ax.axis("off")

    title = recommendation.tipo_grafico or "Visualización"
    columns_text = ", ".join(recommendation.columnas_lista or []) or "N/A"

    ax.text(0.5, 0.90, title, ha="center", va="center", fontsize=22, fontweight="bold")
    ax.text(0.08, 0.76, f"Columnas: {columns_text}", fontsize=12, fontweight="bold")
    ax.text(0.08, 0.65, "Justificación", fontsize=13, fontweight="bold")
    ax.text(0.08, 0.57, wrap_text(recommendation.justificacion or "Sin justificación."), fontsize=11)

    ax.text(0.08, 0.40, "Interpretación sugerida", fontsize=13, fontweight="bold")
    ax.text(
        0.08,
        0.30,
        wrap_text(
            "Utiliza esta visualización para resumir el comportamiento de la(s) variable(s) "
            "seleccionada(s) y documentar los patrones principales que detectes en el dataset."
        ),
        fontsize=11
    )

    pdf.savefig(fig, bbox_inches="tight")
    plt.close(fig)



# Endpoints

@app.get("/api/health")
def health():
    return {
        "ok": True,
        "prolog_disponible": PROLOG_AVAILABLE,
        "facts_file": str(FACTS_FILE),
        "rules_file": str(RULES_FILE),
        "processed_data_file": str(PROCESSED_DATA_FILE),
    }


@app.post("/api/profile")
async def profile_dataset(
    file: UploadFile = File(...),
    separator: str = Form(","),
    encoding: str = Form("utf-8")
):
    try:
        content = await file.read()
        text = content.decode(encoding, errors="replace")
        df = pd.read_csv(StringIO(text), sep=separator)

        profile = build_profile_for_front(df)

        return {
            "rows": int(df.shape[0]),
            "columns": int(df.shape[1]),
            "profile": profile
        }
    except Exception as e:
        return {"error": str(e)}


@app.post("/api/process")
async def process_dataset(
    file: UploadFile = File(...),
    separator: str = Form(","),
    encoding: str = Form("utf-8"),
    null_threshold: float = Form(...),
    remove_high_null_cols: bool = Form(...),
    skip_null_removal: bool = Form(...),
    null_strategy: str = Form(...),
    audience: str = Form(...),
    approved_roles_json: str = Form(...)
):
    try:
        content = await file.read()
        text = content.decode(encoding, errors="replace")
        df = pd.read_csv(StringIO(text), sep=separator)

        approved_roles = json.loads(approved_roles_json)

        df_processed = process_dataframe(
            df=df,
            approved_roles=approved_roles,
            null_threshold=null_threshold,
            remove_high_null_cols=remove_high_null_cols,
            skip_null_removal=skip_null_removal,
            null_strategy=null_strategy
        )

        profile = build_profile_with_approved_roles(df_processed, approved_roles)

        save_prolog_facts(profile, audience, FACTS_FILE)

        recommendations = query_prolog_recommendations(profile)

        save_processed_dataframe(df_processed)
        save_recommendations_cache(recommendations)

        return {
            "rows_processed": int(df_processed.shape[0]),
            "columns_processed": int(df_processed.shape[1]),
            "facts_file": str(FACTS_FILE),
            "rules_file": str(RULES_FILE),
            "recommendations": recommendations
        }

    except Exception as e:
        return {"error": str(e)}


@app.post("/api/report")
async def generate_report(payload: ReportRequest):
    selected = [rec for rec in payload.recommendations if rec.es_grafico]

    if not selected:
        raise HTTPException(
            status_code=400,
            detail="Selecciona al menos una recomendación que sí corresponda a un gráfico."
        )

    df = load_processed_dataframe()

    buffer = BytesIO()

    try:
        with PdfPages(buffer) as pdf:
            build_intro_page(pdf, len(selected))

            for rec in selected:
                build_description_page(pdf, rec)
                fig = build_chart_figure(df, rec)
                pdf.savefig(fig, bbox_inches="tight")
                plt.close(fig)

        buffer.seek(0)
        return StreamingResponse(
            buffer,
            media_type="application/pdf",
            headers={"Content-Disposition": "attachment; filename=reporte_visualizaciones.pdf"}
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"No se pudo generar el reporte: {exc}")

# El dashboard interactivo ahora es provisto por la app Streamlit (streamlit_app.py).
# Ejecutar: streamlit run streamlit_app.py