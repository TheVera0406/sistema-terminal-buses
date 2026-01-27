import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()

def limpiar_base_de_datos():
    conn = None
    try:
        # 1. Conexión a la base de datos
        conn = psycopg2.connect(
            host=os.getenv("DB_HOST"),
            database=os.getenv("DB_NAME"),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASS"),
            port=os.getenv("DB_PORT", "5432")
        )
        cur = conn.cursor()

        # 2. Comando TRUNCATE
        # RESTART IDENTITY: Reinicia los IDs a 1
        # CASCADE: Por si hay llaves foráneas conectadas
        tablas = ['import_salidas', 'import_llegadas', 'noticias','lugares','empresas']
        
        print("Iniciando limpieza de datos...")
        
        for tabla in tablas:
            query = f"TRUNCATE TABLE {tabla} RESTART IDENTITY CASCADE;"
            cur.execute(query)
            print(f"✔️ Tabla {tabla} vaciada e IDs reiniciados.")

        # 3. Confirmar cambios
        conn.commit()
        print("\n Base de datos lista para nuevos registros desde el ID 1.")

        cur.close()

    except Exception as e:
        if conn:
            conn.rollback()
        print(f" Error durante la limpieza: {e}")
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    confirmacion = input(" ¿Estás seguro de que quieres borrar TODOS los datos? (s/n): ")
    if confirmacion.lower() == 's':
        limpiar_base_de_datos()
    else:
        print("Operación cancelada.")