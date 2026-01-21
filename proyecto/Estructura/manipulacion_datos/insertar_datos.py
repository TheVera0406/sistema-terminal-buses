import pandas as pd
import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()

def conectar_db():
    return psycopg2.connect(
        host=os.getenv("DB_HOST"),
        database=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASS"),
        port=os.getenv("DB_PORT", "5432")
    )

def obtener_id_empresa(cursor, nombre_empresa):
    """Verifica si la empresa existe, si no, la crea y retorna el ID."""
    cursor.execute("SELECT id FROM empresas WHERE nombre = %s;", (nombre_empresa,))
    resultado = cursor.fetchone()
    if resultado: 
        return resultado[0]
    else:
        cursor.execute("INSERT INTO empresas (nombre) VALUES (%s) RETURNING id;", (nombre_empresa,))
        return cursor.fetchone()[0]

def obtener_id_lugar(cursor, nombre_lugar):
    """Verifica si el lugar existe, si no, lo crea y retorna el ID (Lógica Espejo)."""
    if not nombre_lugar: return None
    cursor.execute("SELECT id FROM lugares WHERE nombre = %s;", (nombre_lugar,))
    resultado = cursor.fetchone()
    if resultado: 
        return resultado[0]
    else:
        cursor.execute("INSERT INTO lugares (nombre) VALUES (%s) RETURNING id;", (nombre_lugar,))
        return cursor.fetchone()[0]

def insertar_csv_en_tabla(conn, archivo_csv, tabla):
    if not os.path.exists(archivo_csv): return 0

    df = pd.read_csv(archivo_csv, sep=';')
    cur = conn.cursor()
    contador = 0

    # SQL con parámetros seguros para evitar inyección y errores de formato
    sql = f"""
        INSERT INTO {tabla} (lugar, hora, anden, empresa_nombre, fecha)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (fecha, hora, empresa_nombre, lugar) DO NOTHING
    """

    for _, row in df.iterrows():
        # 1. Poblado automático de tablas maestras (Empresas y Lugares)
        obtener_id_empresa(cur, row['empresa'])
        obtener_id_lugar(cur, row['lugar'])
        
        # 2. Inserción del registro de viaje
        cur.execute(sql, (row['lugar'], row['hora'], row['anden'], row['empresa'], row['fecha']))
        if cur.rowcount > 0: 
            contador += 1

    conn.commit()
    cur.close()
    return contador

# --- FUNCIÓN PRINCIPAL LLAMADA DESDE FLASK ---
def ejecutar_insercion_datos(carpeta_uploads):
    conn = conectar_db()
    if not conn: return False, "Error conectando a BD."

    ruta_llegadas = os.path.join(carpeta_uploads, 'llegadas_limpio.csv')
    ruta_salidas = os.path.join(carpeta_uploads, 'salidas_limpio.csv')

    try:
        cont_llegadas = insertar_csv_en_tabla(conn, ruta_llegadas, 'import_llegadas')
        cont_salidas = insertar_csv_en_tabla(conn, ruta_salidas, 'import_salidas')
        
        conn.close()
        return True, f"Se insertaron {cont_llegadas} llegadas y {cont_salidas} salidas correctamente."
    except Exception as e:
        if conn: conn.close()
        return False, f"Error en inserción: {str(e)}"