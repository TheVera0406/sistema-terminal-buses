import psycopg2

# --- DATOS DE CONEXIÓN ---
DB_HOST = "localhost"
DB_NAME = "postgres"
DB_USER = "postgres"
DB_PASS = "vera123"

conn = psycopg2.connect(host=DB_HOST, database=DB_NAME, user=DB_USER, password=DB_PASS)
cur = conn.cursor()

print("🧹 LIMPIANDO BASE DE DATOS...")

try:
    # 1. Eliminar columna 'anio' de LLEGADAS
    print("   -> Eliminando columna 'anio' de import_llegadas...")
    cur.execute("ALTER TABLE import_llegadas DROP COLUMN IF EXISTS anio;")

    # 2. Eliminar columna 'anio' de SALIDAS
    print("   -> Eliminando columna 'anio' de import_salidas...")
    cur.execute("ALTER TABLE import_salidas DROP COLUMN IF EXISTS anio;")

    conn.commit()
    print("\n✨ ¡LISTO! La base de datos está limpia y sin datos redundantes.")

except Exception as e:
    print(f"\n❌ Error: {e}")
    conn.rollback()

conn.close()