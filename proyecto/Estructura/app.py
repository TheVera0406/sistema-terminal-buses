from flask import Flask, render_template, request, redirect, url_for, flash
import psycopg2
from datetime import datetime, timedelta
import os

# IMPORTACIONES DE SEGURIDAD Y LOGIN
from flask_login import LoginManager, login_user, login_required, logout_user, current_user, UserMixin
from werkzeug.security import check_password_hash

# --- 1. IMPORTAR TUS BLUEPRINTS (Tus archivos de rutas) ---
from rutas_admin import admin_bp          # Panel del Jefe
from rutas_recorridos import usuario_bp   # Panel de Pasajeros (Archivo rutas_recorridos.py)
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

# --- 2. CONFIGURACIÓN GENERAL ---
app.secret_key = os.getenv("SECRET_KEY") # Necesaria para login y flash messages

# --- 3. REGISTRAR BLUEPRINTS ---
app.register_blueprint(admin_bp)
app.register_blueprint(usuario_bp)

# --- 4. CONFIGURACIÓN DE LOGIN ---
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login' # Si intentan entrar sin permiso, van aquí

# --- 5. CONFIGURACIÓN BASE DE DATOS ---

def obtener_conexion():
    try:
        conn = psycopg2.connect(
            host=os.getenv("DB_HOST"),
            database=os.getenv("DB_NAME"),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASS"),
            port=os.getenv("DB_PORT", "5432")
        )
        return conn
    except Exception as e:
        print(f" Error conectando a DB: {e}")
        return None

# --- 6. MODELO DE USUARIO ---
class User(UserMixin):
    def __init__(self, id, username, password_hash, rol):
        self.id = id
        self.username = username
        self.password = password_hash
        self.rol = rol

@login_manager.user_loader
def load_user(user_id):
    conn = obtener_conexion()
    if not conn: return None
    cur = conn.cursor()
    cur.execute("SELECT id, username, password, rol FROM usuarios WHERE id = %s", (user_id,))
    usuario_data = cur.fetchone()
    cur.close()
    conn.close()
    
    if usuario_data:
        return User(usuario_data[0], usuario_data[1], usuario_data[2], usuario_data[3])
    return None

# --- 7. FUNCIÓN PARA PANTALLA PÚBLICA (INDEX) ---
def obtener_datos_filtrados(tabla):
    conn = obtener_conexion()
    if not conn: return []

    try:
        cur = conn.cursor()
        
        # SQL Optimizado: La base de datos hace todo el trabajo de filtrado
        # Comprobamos que la fecha sea hoy y que la hora sea mayor a (ahora - 2 horas)
        query = f"""
            SELECT hora, empresa_nombre, lugar, anden 
            FROM {tabla} 
            WHERE fecha = CURRENT_DATE 
              AND hora >= (CURRENT_TIME - INTERVAL '2 hours')
            ORDER BY hora ASC
        """
        cur.execute(query)
        datos = cur.fetchall()

        # Ya no necesitamos el bucle for con ifs, la DB ya nos dio la lista limpia
        resultados = []
        for row in datos:
            hora_str = row[0].strftime('%H:%M') if row[0] else "--:--"
            resultados.append((hora_str, row[1], row[2], row[3]))

        cur.close()
        conn.close()
        return resultados

    except Exception as e:
        print(f" Error en la función obtener_datos_filtrados: {e}")
        return []

# ==========================================
# RUTAS PRINCIPALES DE APP.PY
# ==========================================

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        usuario = request.form['username']
        clave = request.form['password']
        
        conn = obtener_conexion()
        cur = conn.cursor()
        cur.execute("SELECT id, username, password, rol FROM usuarios WHERE username = %s", (usuario,))
        user_data = cur.fetchone()
        cur.close()
        conn.close()

        if user_data and check_password_hash(user_data[2], clave):
            user_obj = User(user_data[0], user_data[1], user_data[2], user_data[3])
            login_user(user_obj)
            
            # --- REDIRECCIÓN SEGÚN ROL ---
            if user_obj.rol == 'admin':
                return redirect(url_for('admin_bp.admin_panel')) # Va al Admin
            else:
                # CORRECCIÓN: Ahora va directo al portal de usuarios
                return redirect(url_for('usuario_bp.dashboard')) 
        else:
            flash('Usuario o contraseña incorrectos', 'danger')
            
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Sesión cerrada correctamente.', 'success')
    return redirect(url_for('login'))

@app.route('/')
def inicio():
    # Pantalla pública (TV del terminal)
    llegadas = obtener_datos_filtrados('import_llegadas')
    salidas = obtener_datos_filtrados('import_salidas')
    noticias = []
    conn = obtener_conexion()
    if conn:
        cur = conn.cursor()
        cur.execute("SELECT contenido FROM noticias ORDER BY id DESC")
        noticias = [row[0] for row in cur.fetchall()]
        cur.close()
        conn.close()

    # Si no hay noticias en la DB, se envia por defecto un saludo
    if not noticias:
        noticias = ["Bienvenido al Terminal de Buses de Coyhaique"]

    return render_template('index.html', 
                           llegadas=llegadas, 
                           salidas=salidas, 
                           noticias_db=noticias) # Envia la lista a la pantalla

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)

