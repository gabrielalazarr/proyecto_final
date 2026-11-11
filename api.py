"""
API del Proyecto Final - Nike Colombia
======================================
Backend (FastAPI) que consulta y administra los 979 productos de Nike Colombia
que obtuvimos con web scraping y limpiamos en el segundo corte.
Los datos viven en MongoDB Atlas (colección productos_nike_limpios).

Cómo ejecutar (con (venv) activo, dentro de esta carpeta):
    python -m uvicorn api:app --reload

Luego abre en el navegador:  http://localhost:8000/docs

IMPORTANTE - Seguridad:
    La cadena de conexión a Mongo NUNCA se escribe en este archivo.
    Se lee de la variable MONGO_URI del archivo .env (que no se sube a GitHub).
"""

import os
from typing import Literal, Optional

import requests
from bson import ObjectId
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field, model_validator
from pymongo import MongoClient

# Si existe un archivo .env, carga sus variables
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

# ---------------------------------------------------------------------------
# 1. CONFIGURACIÓN
# ---------------------------------------------------------------------------
NOMBRE_BD = "scrapers_db"                     # nuestra base de datos en Atlas
NOMBRE_COLECCION = "productos_nike_limpios"   # la colección con los datos limpios

# Campos que existen en cada producto, separados por tipo de dato.
# Los usamos para validar lo que pide el usuario y para convertir los filtros.
CAMPOS_TEXTO = ["nombre", "genero", "tipo", "color_principal", "tallas",
                "disponibilidad", "rango_precio", "url"]
CAMPOS_NUMERICOS = ["precio_normal", "precio_final", "descuento_pct", "num_tallas"]
CAMPOS_SI_NO = ["tiene_descuento"]
TODOS_LOS_CAMPOS = CAMPOS_TEXTO + CAMPOS_NUMERICOS + CAMPOS_SI_NO

# Inteligencia artificial (Gemini): la clave también vive en el archivo .env
import requests  # === NUEVO (IA): para llamar a la API del modelo ===
 
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
MODELO_IA = "gemma-4-26b-a4b-it"   # modelo que respondió 200
 

# ---------------------------------------------------------------------------
# 2. CONEXIÓN A MONGODB (segura: la clave viene del archivo .env)
# ---------------------------------------------------------------------------
MONGO_URI = os.environ.get("MONGO_URI")
if not MONGO_URI:
    raise RuntimeError(
        "Falta la variable de entorno MONGO_URI. "
        "Crea un archivo .env con tu cadena de conexión de Atlas."
    )

cliente = MongoClient(MONGO_URI)
coleccion = cliente[NOMBRE_BD][NOMBRE_COLECCION]

# ---------------------------------------------------------------------------
# 3. LA APLICACIÓN
# ---------------------------------------------------------------------------
app = FastAPI(
    title="API Nike Colombia 👟",
    description=(
        "Consulta y administra los productos de la tienda en línea de Nike Colombia, "
        "obtenidos con web scraping y limpiados en el segundo corte.\n\n"
        "**Lectura:** listar y filtrar productos, ver uno por su id, resumen general "
        "y estadísticas agrupadas.\n\n**Escritura:** agregar un producto nuevo."
    ),
    version="1.0",
)


def _a_json(doc):
    """El _id de Mongo es un objeto especial; lo pasamos a texto para el JSON."""
    doc["_id"] = str(doc["_id"])
    return doc


def _convertir_valor(campo, valor):
    """Lo que llega por la URL siempre es texto ("679950", "true").
    Lo convertimos al tipo real del campo para que Mongo lo encuentre."""
    if campo in CAMPOS_NUMERICOS:
        try:
            numero = float(valor)
        except ValueError:
            raise HTTPException(400, f"El campo '{campo}' es numérico y '{valor}' no es un número.")
        return int(numero) if numero.is_integer() else numero
    if campo in CAMPOS_SI_NO:
        return valor.strip().lower() in ["true", "1", "si", "sí"]
    return valor


@app.get("/", tags=["Inicio"])
def inicio():
    """Mensaje de bienvenida y lista de endpoints."""
    return {
        "mensaje": "API Nike Colombia - ve a /docs para probarla",
        "productos_en_la_base": coleccion.count_documents({}),
        "endpoints": ["GET /datos", "GET /datos/{id}", "GET /resumen",
                      "GET /estadisticas", "POST /datos", "/docs"],
    }


# ==== LEER =================================================================
@app.get("/datos", tags=["Lectura"])
def listar(
    campo: Optional[str] = Query(None, description="Filtro libre: nombre del campo (ej: genero)"),
    valor: Optional[str] = Query(None, description="Filtro libre: valor del campo (ej: Mujer)"),
    genero: Optional[str] = Query(None, description="Hombre, Mujer, Unisex o Niños y niñas"),
    tipo: Optional[str] = Query(None, description="Calzado, Ropa o Accesorios"),
    precio_min: Optional[int] = Query(None, ge=0, description="Precio final mínimo (COP)"),
    precio_max: Optional[int] = Query(None, ge=0, description="Precio final máximo (COP)"),
    solo_descuento: bool = Query(False, description="true = solo productos con descuento"),
    buscar: Optional[str] = Query(None, description="Palabra dentro del nombre (ej: jordan)"),
    ordenar_por: str = Query("precio_final", description="Campo para ordenar"),
    orden: Literal["asc", "desc"] = Query("desc", description="asc = menor a mayor"),
    limite: int = Query(20, ge=1, le=1000, description="Máximo de productos a devolver"),
):
    """Lista productos con filtros combinables.

    Ejemplos:
        /datos?genero=Mujer&tipo=Calzado
        /datos?solo_descuento=true&precio_max=300000
        /datos?buscar=jordan&orden=asc
        /datos?campo=disponibilidad&valor=Agotado
    """
    filtro = {}

    # Filtro libre campo = valor (el que usa el dashboard del profesor)
    if campo and valor:
        if campo not in TODOS_LOS_CAMPOS:
            raise HTTPException(400, f"El campo '{campo}' no existe. Opciones: {TODOS_LOS_CAMPOS}")
        filtro[campo] = _convertir_valor(campo, valor)

    # Filtros específicos de Nike
    if genero:
        filtro["genero"] = genero
    if tipo:
        filtro["tipo"] = tipo
    if solo_descuento:
        filtro["tiene_descuento"] = True
    if buscar:
        # $regex busca la palabra dentro del nombre; "i" = sin importar mayúsculas
        filtro["nombre"] = {"$regex": buscar, "$options": "i"}
    if precio_min is not None or precio_max is not None:
        filtro["precio_final"] = {}
        if precio_min is not None:
            filtro["precio_final"]["$gte"] = precio_min   # mayor o igual
        if precio_max is not None:
            filtro["precio_final"]["$lte"] = precio_max   # menor o igual

    if ordenar_por not in TODOS_LOS_CAMPOS:
        raise HTTPException(400, f"No se puede ordenar por '{ordenar_por}'.")
    direccion = 1 if orden == "asc" else -1

    documentos = [_a_json(d) for d in
                  coleccion.find(filtro).sort(ordenar_por, direccion).limit(limite)]
    return {
        "cantidad": len(documentos),
        "total_que_cumplen": coleccion.count_documents(filtro),
        "datos": documentos,
    }


@app.get("/datos/{id}", tags=["Lectura"])
def ver_uno(id: str):
    """Devuelve un solo producto por su _id de Mongo."""
    if not ObjectId.is_valid(id):
        raise HTTPException(400, "El id no tiene el formato de un id de Mongo.")
    doc = coleccion.find_one({"_id": ObjectId(id)})
    if doc is None:
        raise HTTPException(404, "No existe un producto con ese id.")
    return _a_json(doc)


@app.get("/resumen", tags=["Lectura"])
def resumen():
    """Cifras generales del catálogo (para las tarjetas del dashboard)."""
    total = coleccion.count_documents({})
    if total == 0:
        raise HTTPException(404, "La colección está vacía.")
    con_descuento = coleccion.count_documents({"tiene_descuento": True})
    agotados = coleccion.count_documents({"disponibilidad": "Agotado"})

    precios = list(coleccion.aggregate([
        {"$group": {"_id": None,
                    "promedio": {"$avg": "$precio_final"},
                    "minimo": {"$min": "$precio_final"},
                    "maximo": {"$max": "$precio_final"}}}
    ]))[0]
    descuento = list(coleccion.aggregate([
        {"$match": {"tiene_descuento": True}},
        {"$group": {"_id": None, "promedio": {"$avg": "$descuento_pct"}}},
    ]))

    return {
        "total_productos": total,
        "con_descuento": con_descuento,
        "pct_con_descuento": round(con_descuento / total * 100, 1),
        "descuento_promedio_pct": round(descuento[0]["promedio"], 1) if descuento else 0,
        "agotados": agotados,
        "precio_promedio": round(precios["promedio"]),
        "precio_minimo": precios["minimo"],
        "precio_maximo": precios["maximo"],
    }


@app.get("/estadisticas", tags=["Lectura"])
def estadisticas(
    agrupar_por: str = Query(..., description="Campo de texto (ej: genero, tipo, rango_precio)"),
    sumar: str = Query(..., description="Campo numérico (ej: precio_final, num_tallas)"),
):
    """Agrupa por un campo y calcula suma, promedio, mínimo, máximo y conteo
    de otro (agregación de MongoDB).

    Ejemplos:
        /estadisticas?agrupar_por=genero&sumar=precio_final
        /estadisticas?agrupar_por=tipo&sumar=descuento_pct
    """
    if agrupar_por not in CAMPOS_TEXTO + CAMPOS_SI_NO:
        raise HTTPException(400, f"'{agrupar_por}' no sirve para agrupar. Usa uno de: {CAMPOS_TEXTO}")
    if sumar not in CAMPOS_NUMERICOS:
        raise HTTPException(400, f"'{sumar}' no es numérico. Usa uno de: {CAMPOS_NUMERICOS}")

    pipeline = [
        {
            "$group": {
                "_id": f"${agrupar_por}",           # un grupo por cada valor distinto
                "suma": {"$sum": f"${sumar}"},
                "promedio": {"$avg": f"${sumar}"},
                "minimo": {"$min": f"${sumar}"},
                "maximo": {"$max": f"${sumar}"},
                "conteo": {"$sum": 1},             # cuántos productos hay en el grupo
            }
        },
        {"$sort": {"conteo": -1}},                 # primero el grupo más grande
    ]
    grupos = [
        {
            agrupar_por: r["_id"],
            "suma": r["suma"],
            "promedio": round(r["promedio"], 1),
            "minimo": r["minimo"],
            "maximo": r["maximo"],
            "conteo": r["conteo"],
        }
        for r in coleccion.aggregate(pipeline)
    ]
    return {"grupos": grupos}


# ==== CREAR ================================================================
class NuevoProducto(BaseModel):
    """Lo que el usuario debe enviar para crear un producto.
    Pydantic revisa los tipos y las reglas; si algo está mal, responde 422."""

    nombre: str = Field(min_length=2, max_length=120)
    genero: Literal["Hombre", "Mujer", "Unisex", "Niños y niñas"]
    tipo: Literal["Calzado", "Ropa", "Accesorios"]
    color_principal: str = Field(min_length=3, max_length=30)
    precio_normal: int = Field(gt=0, le=10_000_000, description="Precio antes de descuento (COP)")
    precio_final: int = Field(gt=0, le=10_000_000, description="Precio que se paga (COP)")
    tallas: str = Field("Agotado", description='Tallas separadas por coma, ej: "7, 8, 9.5"')
    url: Optional[str] = None

    @model_validator(mode="after")
    def revisar_precios(self):
        # Mismo criterio de la limpieza: el precio final no puede ser mayor al normal
        if self.precio_final > self.precio_normal:
            raise ValueError("El precio final no puede ser mayor que el precio normal.")
        return self

    model_config = {
        "json_schema_extra": {
            "example": {
                "nombre": "Nike Air Max 90",
                "genero": "Mujer",
                "tipo": "Calzado",
                "color_principal": "Blanco",
                "precio_normal": 599950,
                "precio_final": 479960,
                "tallas": "6, 6.5, 7, 8",
                "url": "https://www.nike.com.co/ejemplo/p",
            }
        }
    }


def _rango(precio):
    if precio < 200000:
        return "Menos de 200 mil"
    if precio < 400000:
        return "200-400 mil"
    if precio < 600000:
        return "400-600 mil"
    return "Más de 600 mil"


@app.post("/datos", status_code=201, tags=["Escritura"])
def crear(producto: NuevoProducto):
    """Agrega un producto nuevo. Las columnas derivadas (descuento, número de
    tallas, disponibilidad, rango de precio) las calcula la API, igual que en
    la limpieza, para que el producto nuevo quede con el mismo formato."""
    doc = producto.model_dump()

    if doc["url"] and coleccion.find_one({"url": doc["url"]}):
        raise HTTPException(409, "Ya existe un producto con esa URL.")

    # Columnas derivadas
    tallas = doc["tallas"].strip()
    doc["num_tallas"] = 0 if tallas in ["", "Agotado"] else len(tallas.split(","))
    if doc["num_tallas"] == 0:
        doc["tallas"] = "Agotado"
        doc["disponibilidad"] = "Agotado"
    elif doc["num_tallas"] <= 3:
        doc["disponibilidad"] = "Pocas tallas (1-3)"
    else:
        doc["disponibilidad"] = "Buena disponibilidad (4+)"

    doc["tiene_descuento"] = doc["precio_final"] < doc["precio_normal"]
    doc["descuento_pct"] = round((doc["precio_normal"] - doc["precio_final"])
                                 / doc["precio_normal"] * 100, 1)
    doc["rango_precio"] = _rango(doc["precio_final"])

    resultado = coleccion.insert_one(doc)
    return {"mensaje": "Producto creado", "id": str(resultado.inserted_id)}


# === NUEVO (IA): preguntar a los datos en lenguaje natural =================
class Pregunta(BaseModel):
    pregunta: str

    model_config = {
        "json_schema_extra": {
            "example": {"pregunta": "¿Cuál sucursal vendió más?"}
        }
    }


@app.post("/preguntar")
def preguntar(p: Pregunta):
    """Responde una pregunta en lenguaje natural usando los datos de la coleccion."""
    if not GEMINI_API_KEY:
        raise HTTPException(status_code=503, detail="Falta la GEMINI_API_KEY.")

    # 1. Una muestra de los datos como contexto para la IA
    muestra = [_a_json(d) for d in coleccion.find().limit(30)]

    # 2. El prompt: instrucciones + datos + pregunta
    prompt = (
        "Eres un asistente que responde preguntas sobre estos datos. "
        "Responde en español, breve y claro. Si la respuesta no está en los datos, dilo.\n\n"
        f"DATOS (muestra):\n{muestra}\n\nPREGUNTA: {p.pregunta}"
    )

    # 3. Llamamos a la API del modelo (¡es otra API REST!)
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{MODELO_IA}:generateContent?key={GEMINI_API_KEY}"
    )
    try:
        r = requests.post(
            url, json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=30
        )
        r.raise_for_status()
        data = r.json()
        respuesta = data["candidates"][0]["content"]["parts"][0]["text"]
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Error al llamar al modelo: {e}")

    return {"respuesta": respuesta}
# === FIN NUEVO (IA) ========================================================