# Agente Inteligente de Perfilado y Recomendación Visual

Este proyecto implementa un agente inteligente diseñado para analizar datasets en formato CSV y recomendar las mejores visualizaciones posibles utilizando un motor de inferencia basado en **Prolog**.

## Definición del Agente
El sistema se formaliza como un agente inteligente que opera de la siguiente manera:
- **Estado ($S$):** Perfil del dataset (tipos de datos, nulos, unicidad) y la audiencia seleccionada (Técnica, Ejecutiva, No Técnica).
- **Acciones ($A$):** Conjunto de visualizaciones recomendadas (Histogramas, Boxplots, KPIs, etc.).
- **Lógica de Decisión ($f$):** Un sistema basado en reglas en Prolog que optimiza la recomendación según las mejores prácticas de visualización de datos y el nivel de la audiencia.

## Tecnologías Utilizadas
- **Backend:** FastAPI (Python)
- **Frontend:** Streamlit + Plotly
- **Motor de Inferencia:** SWI-Prolog (vía `pyswip`)
- **Procesamiento de Datos:** Pandas

## Instrucciones de Ejecución

### 1. Requisitos Previos
- Tener instalado [SWI-Prolog](https://www.swi-prolog.org/).
- Python 3.10 o superior.

### 2. Instalación de Dependencias
Se recomienda utilizar un entorno virtual:
```bash
python -m venv .venv
source .venv/bin/activate  # En Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Ejecutar el Sistema
El sistema requiere que tanto el backend como el frontend estén activos:

**Servidor Backend (FastAPI):**
```bash
cd backend
python -m uvicorn main:app --port 8000
```

**Dashboard Frontend (Streamlit):**
```bash
# En una nueva terminal, desde la raíz del proyecto:
python -m streamlit run streamlit_app.py
```

## Estructura del Repositorio
- `backend/`: Servidor FastAPI y lógica principal.
  - `prolog/`: Contiene `reglas.pl` (el cerebro del agente).
  - `frontend/`: Versión estática opcional del frontend.
  - `temp/`: Almacenamiento temporal de datos procesados.
- `streamlit_app.py`: Interfaz interactiva de usuario.
- `requirements.txt`: Lista de dependencias de Python.

## Ejemplo de Uso
1. Inicie la aplicación y acceda a `http://localhost:8501`.
2. Cargue un archivo CSV (ej. `datos_ventas.csv`).
3. Seleccione la audiencia (ej. **Ejecutiva**).
4. El agente recomendará automáticamente **KPIs** y **Gráficos de Pastel** en lugar de histogramas técnicos.
5. Seleccione los gráficos deseados y genere un reporte en PDF.
