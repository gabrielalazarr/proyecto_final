# 👟 Nike Colombia — Aplicación de datos

Proyecto final de **Programación Aplicada (Ciencia de Datos)**.

Tomamos **979 productos** de la tienda en línea de Nike Colombia (nike.com.co), obtenidos con
**web scraping** y limpiados en el segundo corte, y los convertimos en una aplicación completa:

```
MongoDB Atlas  ──>  API (FastAPI)  ──>  Dashboard (Streamlit)
  los datos          el backend            el frontend
```

## ¿Qué hace cada archivo?

| Archivo | Para qué sirve |
|---|---|
| `cargar_datos_limpios.py` | Lee los productos crudos del scraping en Mongo, los limpia (precios a número, género, tipo, disponibilidad, rango de precio) y los guarda en la colección `productos_nike_limpios`. |
| `api.py` | La API. Lee y escribe en Mongo. Endpoints: `GET /datos`, `GET /datos/{id}`, `GET /resumen`, `GET /estadisticas`, `POST /datos` y `POST /preguntar` (IA con Gemini). |
| `dashboard.py` | La página web. Muestra cifras, filtra productos, grafica estadísticas, permite agregar productos y preguntarle a los datos con IA. |
| `requirements.txt` | Librerías necesarias. |
| `.env.example` | Plantilla de las claves (el `.env` real **no** se sube a GitHub). |

## Cómo ejecutarlo

```bash
# 1. Entorno virtual
py -m venv venv
.\venv\Scripts\Activate.ps1        # Mac/Linux: source venv/bin/activate
pip install -r requirements.txt

# 2. Claves: copiar la plantilla y llenarla
copy .env.example .env             # Mac/Linux: cp .env.example .env

# 3. (Solo la primera vez) cargar los datos limpios en Mongo
python cargar_datos_limpios.py

# 4. Terminal 1: la API  ->  http://localhost:8000/docs
python -m uvicorn api:app --reload

# 5. Terminal 2: el dashboard  ->  http://localhost:8501
python -m streamlit run dashboard.py
```

## Datos

- **Fuente:** páginas de producto de https://www.nike.com.co (scraping con la API pública de VTEX).
- **Base de datos:** `scrapers_db` en MongoDB Atlas.
  - `productos_nike`: datos crudos del scraping.
  - `productos_nike_limpios`: datos limpios que usa la API.
- **Limitaciones:** datos de un solo día; el género de 257 productos se dedujo por las tallas; el tipo se dedujo del nombre y las tallas.

## Seguridad

Las contraseñas (MongoDB y Gemini) viven solo en el archivo `.env`, que está en `.gitignore`.
Nunca se escriben dentro del código.
