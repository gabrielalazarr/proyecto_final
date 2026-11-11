"""
cargar_datos_limpios.py
=======================
Toma los productos CRUDOS del scraping (colección productos_nike),
los limpia con las mismas decisiones del segundo corte
y los guarda en una colección NUEVA: productos_nike_limpios.

Esa colección limpia es la que va a usar la API del proyecto final.

Cómo ejecutarlo (con (venv) activo):
    python cargar_datos_limpios.py
"""

import os
import re

import pandas as pd
from dotenv import load_dotenv
from pymongo import MongoClient

# ------------------------------------------------------------
# 1) CONEXIÓN A MONGO (la contraseña se lee del archivo .env)
# ------------------------------------------------------------
load_dotenv()                          # lee el archivo .env
MONGO_URI = os.getenv("MONGO_URI")     # toma la línea MONGO_URI=...
if not MONGO_URI:
    raise RuntimeError("Falta la variable MONGO_URI en el archivo .env")

cliente = MongoClient(MONGO_URI)
cliente.admin.command("ping")          # si la conexión falla, aquí sale el error
print("✅ Conectado a MongoDB Atlas")

db = cliente["scrapers_db"]
crudos = db["productos_nike"]           # lo que guardó el scraping
limpios = db["productos_nike_limpios"]  # donde vamos a guardar lo limpio

# ------------------------------------------------------------
# 2) TRAER LOS DATOS CRUDOS A PANDAS
# ------------------------------------------------------------
df = pd.DataFrame(list(crudos.find({}, {"_id": 0})))
print("Productos crudos:", len(df))

# Nombres de columnas sin tildes ni espacios
df = df.rename(columns={
    "Nombre": "nombre",
    "Género": "genero",
    "Color": "color",
    "Precio Normal": "precio_normal",
    "Precio Descuento": "precio_descuento",
    "Tallas Disponibles": "tallas",
    "URL": "url",
})

# ------------------------------------------------------------
# 3) LIMPIEZA (las mismas decisiones del segundo corte)
# ------------------------------------------------------------

# Precios: de texto "$679,950" a número 679950
def limpiar_precio(texto):
    if isinstance(texto, (int, float)):
        return texto
    if pd.isnull(texto) or "$" not in str(texto):
        return None                    # "Sin descuento" o "No disponible"
    return float(str(texto).replace("$", "").replace(",", "").strip())

df["precio_normal"] = df["precio_normal"].apply(limpiar_precio)
df["precio_descuento"] = df["precio_descuento"].apply(limpiar_precio)

# Sin precio normal no sirve: se elimina
df = df.dropna(subset=["precio_normal"])

# Si no tiene descuento, el cliente paga el precio normal
df["precio_final"] = df["precio_descuento"].fillna(df["precio_normal"])

# Texto: quitar espacios y sacar el color principal ("Negro, Blanco" -> "Negro")
df["nombre"] = df["nombre"].str.strip()
df["color"] = df["color"].replace("No especificado", "Sin dato")
df["color_principal"] = df["color"].str.split(",").str[0].str.strip().str.capitalize()

# Duplicados por URL
df = df.drop_duplicates(subset=["url"])

# Género: completar "No especificado" usando las tallas (Y/C = niños)
def ajustar_genero(fila):
    if fila["genero"] in ["Hombre", "Mujer", "Unisex"]:
        return fila["genero"]
    nombre = str(fila["nombre"]).lower()
    if "niño" in nombre or "niña" in nombre or "kids" in nombre:
        return "Niños y niñas"
    for talla in str(fila["tallas"]).upper().split(","):
        if re.fullmatch(r"\d+(\.\d+)?[YC]", talla.strip()):
            return "Niños y niñas"
    return "Unisex"

df["genero"] = df.apply(ajustar_genero, axis=1)

# ------------------------------------------------------------
# 4) COLUMNAS NUEVAS
# ------------------------------------------------------------
df["tiene_descuento"] = df["precio_final"] < df["precio_normal"]
df["descuento_pct"] = ((df["precio_normal"] - df["precio_final"]) / df["precio_normal"] * 100).round(1)

df["num_tallas"] = df["tallas"].apply(lambda t: 0 if t == "Agotado" else len(str(t).split(",")))

def sacar_tipo(fila):
    nombre = str(fila["nombre"]).lower()
    accesorios = ["balón", "balon", "gorra", "cap", "medias", "maleta", "bolsa", "canilleras",
                  "guantes", "visera", "morral", "mochila", "botella"]
    if any(palabra in nombre for palabra in accesorios):
        return "Accesorios"
    if fila["tallas"] == "Agotado":
        return "Sin dato"
    primera = str(fila["tallas"]).split(",")[0].strip().upper()
    if primera in ["XS", "S", "M", "L", "XL", "XXL", "2XL", "3XL"]:
        return "Ropa"
    if "MISC" in primera:
        return "Accesorios"
    return "Calzado"

df["tipo"] = df.apply(sacar_tipo, axis=1)

def disponibilidad(n):
    if n == 0:
        return "Agotado"
    if n <= 3:
        return "Pocas tallas (1-3)"
    return "Buena disponibilidad (4+)"

df["disponibilidad"] = df["num_tallas"].apply(disponibilidad)

df["rango_precio"] = pd.cut(df["precio_final"],
                            bins=[0, 200000, 400000, 600000, float("inf")],
                            labels=["Menos de 200 mil", "200-400 mil", "400-600 mil", "Más de 600 mil"]).astype(str)

# ------------------------------------------------------------
# 5) GUARDAR EN LA COLECCIÓN NUEVA
# ------------------------------------------------------------
columnas = ["nombre", "genero", "tipo", "color_principal",
            "precio_normal", "precio_final", "descuento_pct", "tiene_descuento",
            "tallas", "num_tallas", "disponibilidad", "rango_precio", "url"]
df = df[columnas]

# Convertimos cada fila a tipos normales de Python (Mongo no acepta los de numpy)
registros = []
for fila in df.to_dict("records"):
    registros.append({
        "nombre": fila["nombre"],
        "genero": fila["genero"],
        "tipo": fila["tipo"],
        "color_principal": fila["color_principal"],
        "precio_normal": int(fila["precio_normal"]),
        "precio_final": int(fila["precio_final"]),
        "descuento_pct": float(fila["descuento_pct"]),
        "tiene_descuento": bool(fila["tiene_descuento"]),
        "tallas": fila["tallas"],
        "num_tallas": int(fila["num_tallas"]),
        "disponibilidad": fila["disponibilidad"],
        "rango_precio": fila["rango_precio"],
        "url": fila["url"],
    })

limpios.delete_many({})                 # si se corre otra vez, no se duplica nada
limpios.insert_many(registros)

print("✅ Productos limpios guardados:", limpios.count_documents({}))
print("\nPor género:")
print(df["genero"].value_counts().to_string())
print("\nEjemplo de un producto:")
print(limpios.find_one({}, {"_id": 0}))