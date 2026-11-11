"""
Dashboard del Proyecto Final - Nike Colombia
============================================
Frontend (Streamlit) que consume la API (api.py): lista, filtra, grafica
y permite agregar productos nuevos.

Como ejecutar (en OTRA terminal, con la API ya corriendo):
    python -m streamlit run dashboard.py

La API debe estar activa en http://localhost:8000
"""

import pandas as pd
import requests
import streamlit as st

#API = "http://localhost:8000"  # 👈 si despliegas la API en la nube, cambia esta URL
API = "http://127.0.0.1:8000"

st.set_page_config(page_title="Nike Colombia", page_icon="👟", layout="wide")
st.title("👟 Dashboard Nike Colombia")
st.write("Productos de nike.com.co obtenidos con web scraping, limpiados y servidos por nuestra API.")


# --- Funciones que hablan con la API ---------------------------------------
@st.cache_data(ttl=30)
def listar(campo=None, valor=None, limite=1000):
    params = {"limite": limite}
    if campo and valor:
        params.update({"campo": campo, "valor": valor})
    r = requests.get(f"{API}/datos", params=params, timeout=10)
    r.raise_for_status()
    return pd.DataFrame(r.json()["datos"])


@st.cache_data(ttl=30)
def estadisticas(agrupar_por, sumar):
    r = requests.get(
        f"{API}/estadisticas",
        params={"agrupar_por": agrupar_por, "sumar": sumar},
        timeout=10,
    )
    r.raise_for_status()
    return pd.DataFrame(r.json()["grupos"])


# --- Verifica que la API este arriba ---------------------------------------
try:
    df = listar()
except Exception:
    st.error(
        f"No pude conectarme a la API en {API}. "
        f"Revisa que este corriendo:  python -m uvicorn api:app --reload"
    )
    st.stop()

if df.empty:
    st.warning("La coleccion esta vacia.")
    st.stop()

# Campos de texto que tiene sentido usar para filtrar y agrupar
categoricas = ["genero", "tipo", "color_principal", "disponibilidad", "rango_precio"]
# Campos numericos de nuestros productos
numericas = ["precio_final", "precio_normal", "descuento_pct", "num_tallas"]

# --- Filtro en la barra lateral --------------------------------------------
st.sidebar.header("Filtros")
campo = st.sidebar.selectbox("Filtrar por campo", ["(todos)"] + categoricas)
if campo != "(todos)":
    opciones = sorted(df[campo].dropna().astype(str).unique())
    valor = st.sidebar.selectbox("Valor", opciones)
    df = listar(campo=campo, valor=valor)

# --- Metricas ---------------------------------------------------------------
c1, c2, c3 = st.columns(3)
c1.metric("Productos", len(df))
c2.metric("Precio promedio", f"${df['precio_final'].mean():,.0f}".replace(",", "."))
c3.metric("Con descuento", int(df["tiene_descuento"].sum()))

# --- Estadisticas (usa la agregacion de la API) ----------------------------
st.subheader("Estadisticas")
a1, a2 = st.columns(2)
agrupar = a1.selectbox("Agrupar por", categoricas)
sumar = a2.selectbox("Calcular sobre", numericas)
if st.button("Calcular"):
    g = estadisticas(agrupar, sumar)
    st.write(f"Promedio de **{sumar}** por **{agrupar}**")
    st.bar_chart(g.set_index(agrupar)["promedio"], color="#FA5400")
    st.dataframe(g, width="stretch")

# --- Tabla de datos ---------------------------------------------------------
st.subheader("Datos")
st.dataframe(df.drop(columns=["_id"]), width="stretch")

# === NUEVO (IA): pregúntale a tus datos ====================================
st.subheader("🤖 Pregúntale a tus datos")
pregunta = st.text_input("Escribe tu pregunta (ej. ¿cuál sucursal vendió más?)")
if st.button("Preguntar") and pregunta:
    with st.spinner("Pensando..."):
        r = requests.post(f"{API}/preguntar", json={"pregunta": pregunta}, timeout=60)
    if r.ok:
        st.success(r.json()["respuesta"])
    else:
        st.error(f"Error: {r.text}")
# === FIN NUEVO (IA) ========================================================

# --- Agregar un producto (POST a la API) -----------------------------------
# Los campos son los mismos que pide la API (clase NuevoProducto en api.py).
st.subheader("➕ Agregar producto")
with st.form("nuevo"):
    nombre = st.text_input("nombre")
    genero = st.selectbox("genero", ["Hombre", "Mujer", "Unisex", "Niños y niñas"])
    tipo = st.selectbox("tipo", ["Calzado", "Ropa", "Accesorios"])
    color_principal = st.text_input("color_principal")
    precio_normal = st.number_input("precio_normal", min_value=0, step=10000)
    precio_final = st.number_input("precio_final", min_value=0, step=10000)
    tallas = st.text_input("tallas (separadas por coma, ej: 7, 8, 9)")
    enviar = st.form_submit_button("Guardar")

if enviar:
    payload = {
        "nombre": nombre,
        "genero": genero,
        "tipo": tipo,
        "color_principal": color_principal,
        "precio_normal": int(precio_normal),
        "precio_final": int(precio_final),
        "tallas": tallas or "Agotado",
    }
    r = requests.post(f"{API}/datos", json=payload, timeout=10)
    if r.ok:
        st.success(f"Guardado con id {r.json()['id']}")
        st.cache_data.clear()  # refresca la tabla
    else:
        st.error(f"Error de la API: {r.text}")
