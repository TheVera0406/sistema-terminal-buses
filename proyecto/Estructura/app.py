from flask import Flask, render_template, request, redirect, url_for, flash
import psycopg2
from datetime import datetime, timedelta
import os

# SEGURIDAD Y LOGIN
from flask_login import LoginManager, login_user, login_required, logout_user, current_user, UserMixin
from werkzeug.security import check_password_hash
from dotenv import load_dotenv

# --- 1. IMPORTACIÓN DE BLUEPRINTS ---
from rutas_admin import admin_bp          
from rutas_recorridos import usuario_bp   
from rutas_operador import operador_bp  # <--- NUEVO: Importamos el módulo del operador

load_dotenv()

app = Flask(__name__)
# SEGURIDAD: Solo usa el .env
app.secret_key = os.getenv("SECRET_KEY") 

# --- 2. REGISTRO DE BLUEPRINTS ---
app.register_blueprint(admin_bp)
app.register_blueprint(usuario_bp)
app.register_blueprint(operador_bp)     # <--- NUEVO: Registramos el blueprint

# --- 3. CONFIGURACIÓN LOGIN ---
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login' 

login_manager.login_message = "Por favor, inicia sesión para acceder a esta página."
login_manager.login_message_category = "danger"

class User(UserMixin):
    def __init__(self, id, username, password, rol):
        self.id = id
        self.username = username
        self.password = password
        self.rol = rol

@login_manager.user_loader
def load_user(user_id):
    conn = obtener_conexion()
    if not conn: return None
    cur = conn.cursor()
    cur.execute("SELECT id, username, password, rol FROM usuarios WHERE id = %s", (user_id,))
    user_data = cur.fetchone()
    cur.close()
    conn.close()
    if user_data:
        return User(user_data[0], user_data[1], user_data[2], user_data[3])
    return None

def obtener_conexion():
    try:
        return psycopg2.connect(
            host=os.getenv("DB_HOST"),
            database=os.getenv("DB_NAME"),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASS"),
            port=os.getenv("DB_PORT", "5432")
        )
    except Exception as e:
        print(f"Error DB: {e}")
        return None

# --- 4. FUNCIÓN PARA PANTALLA PÚBLICA (TV) ---
def obtener_datos_filtrados(tabla):
    conn = obtener_conexion()
    if not conn: return []
    cur = conn.cursor()
    
    ahora = datetime.now()
    inicio_ventana = ahora - timedelta(hours=2)
    fin_ventana = ahora + timedelta(hours=12)
    
    # Lógica Timestamp
    query = f"""
        SELECT fecha, hora, empresa_nombre, lugar, anden, estado 
        FROM {tabla} 
        WHERE (fecha + hora) BETWEEN %s AND %s
        ORDER BY fecha ASC, hora ASC
    """
    
    try:
        cur.execute(query, (inicio_ventana, fin_ventana))
        datos = cur.fetchall()
    except Exception as e:
        print(f"Error consulta: {e}")
        datos = []
    
    cur.close()
    conn.close()
    return datos

@app.route('/')
def inicio():
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

    if not noticias:
        noticias = ["Bienvenido al Terminal de Buses de Coyhaique"]

    return render_template('index.html', 
                           llegadas=llegadas, 
                           salidas=salidas, 
                           noticias_db=noticias)

# --- 5. LOGUEO CON REDIRECCIÓN INTELIGENTE ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        usuario = request.form['username']
        clave = request.form['password']
        
        conn = obtener_conexion()
        if conn:
            cur = conn.cursor()
            cur.execute("SELECT id, username, password, rol FROM usuarios WHERE username = %s", (usuario,))
            user_data = cur.fetchone()
            cur.close()
            conn.close()

            if user_data and check_password_hash(user_data[2], clave):
                user_obj = User(user_data[0], user_data[1], user_data[2], user_data[3])
                login_user(user_obj)
                
                # --- AQUÍ ESTÁ EL CAMBIO PRINCIPAL ---
                if user_obj.rol == 'operador':
                    # Si es operador, va directo a SU panel
                    return redirect(url_for('operador_bp.panel_operador'))
                elif user_obj.rol == 'admin':
                    # Si es admin, va al panel general
                    return redirect(url_for('admin_bp.admin_panel'))
                else:
                    # Cualquier otro rol va a la vista pública
                    return redirect(url_for('usuario_bp.dashboard')) 
            else:
                flash('Usuario o contraseña incorrectos', 'danger')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Sesión cerrada.', 'success')
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True)