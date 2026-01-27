import psycopg2
from werkzeug.security import generate_password_hash

# Configuración DB (Recuerda que también puedes usar os.getenv si quieres usar tu .env)
DB_HOST = "localhost"
DB_NAME = "postgres"
DB_USER = "postgres"
DB_PASS = "vera123"

def crear_usuario(username, password, rol):
    # Validación de seguridad para los roles permitidos
    roles_permitidos = ['admin', 'operador']
    if rol not in roles_permitidos:
        print(f" Error: El rol '{rol}' no es válido. Usa 'admin' o 'operador'.")
        return

    try:
        conn = psycopg2.connect(host=DB_HOST, database=DB_NAME, user=DB_USER, password=DB_PASS)
        cur = conn.cursor()

        # 1. Encriptar la contraseña
        password_hash = generate_password_hash(password)

        # 2. Insertar
        sql = "INSERT INTO usuarios (username, password, rol) VALUES (%s, %s, %s)"
        cur.execute(sql, (username, password_hash, rol))
        
        conn.commit()
        print(f" Usuario '{username}' con rol '{rol}' creado exitosamente.")
        cur.close()
        conn.close()
    except Exception as e:
        print(f" Error: {e}")

# --- EJECTUA CAMBIANDO LOS DATOS ---
#if __name__ == "__main__":

    #crear_usuario("vera2", "vera12345", "operador") 
    
    # CAMBIAR DE ESTA MANERA: crear_usuario("nombre de usuario", "clave", "rol (solamente admin o operador)")

