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
    cursor.execute("SELECT id FROM empresas WHERE nombre = %s;", (nombre_empresa,))
    resultado = cursor.fetchone()
    if resultado: 
        return resultado[0]
    else:
        cursor.execute("INSERT INTO empresas (nombre) VALUES (%s) RETURNING id;", (nombre_empresa,))
        return cursor.fetchone()[0]

def obtener_id_lugar(cursor, nombre_lugar):
    if not nombre_lugar: return None
    cursor.execute("SELECT id FROM lugares WHERE nombre = %s;", (nombre_lugar,))
    resultado = cursor.fetchone()
    if resultado: 
        return resultado[0]
    else:
        cursor.execute("INSERT INTO lugares (nombre) VALUES (%s) RETURNING id;", (nombre_lugar,))
        return cursor.fetchone()[0]

def insertar_csv_en_tabla(conn, archivo_csv, tabla):
    if not os.path.exists(archivo_csv): 
        return 0, 0 # Insertados, Duplicados

    try:
        df = pd.read_csv(archivo_csv, sep=';')
    except:
        return 0, 0

    if df.empty: return 0, 0

    cur = conn.cursor()
    insertados = 0
    total_filas = len(df)

    # --- CAMBIO IMPORTANTE AQUÍ ---
    # Agregamos la columna 'estado' y le forzamos el valor 'Programado'
    sql = f"""
        INSERT INTO {tabla} (lugar, hora, anden, empresa_nombre, fecha, estado)
        VALUES (%s, %s, %s, %s, %s, 'Programado')
        ON CONFLICT (fecha, hora, empresa_nombre, lugar) DO NOTHING
    """

    for _, row in df.iterrows():
        obtener_id_empresa(cur, row['empresa'])
        obtener_id_lugar(cur, row['lugar'])
        
        cur.execute(sql, (row['lugar'], row['hora'], row['anden'], row['empresa'], row['fecha']))
        
        if cur.rowcount > 0: 
            insertados += 1

    conn.commit()
    cur.close()
    
    duplicados = total_filas - insertados
    return insertados, duplicados

def ejecutar_insercion_datos(carpeta_uploads):
    conn = conectar_db()
    if not conn: return False, ["Error crítico conectando a BD."]

    ruta_llegadas = os.path.join(carpeta_uploads, 'llegadas_limpio.csv')
    ruta_salidas = os.path.join(carpeta_uploads, 'salidas_limpio.csv')

    mensajes = []
    
    try:
        ins_llegadas, dup_llegadas = insertar_csv_en_tabla(conn, ruta_llegadas, 'import_llegadas')
        ins_salidas, dup_salidas = insertar_csv_en_tabla(conn, ruta_salidas, 'import_salidas')
        
        conn.close()
        
        # Mensajes sin emojis (según tu configuración anterior)
        if ins_llegadas > 0:
            mensajes.append(f"Éxito: {ins_llegadas} nuevas llegadas insertadas.")
        if dup_llegadas > 0:
            mensajes.append(f"Advertencia: {dup_llegadas} llegadas duplicadas omitidas.")
            
        if ins_salidas > 0:
            mensajes.append(f"Éxito: {ins_salidas} nuevas salidas insertadas.")
        if dup_salidas > 0:
            mensajes.append(f"Advertencia: {dup_salidas} salidas duplicadas omitidas.")

        if ins_llegadas == 0 and ins_salidas == 0 and dup_llegadas == 0 and dup_salidas == 0:
             return False, ["No se encontraron datos válidos para insertar."]

        return True, mensajes

    except Exception as e:
        if conn: conn.close()
        return False, [f"Error base de datos: {str(e)}"]