from flask import Flask, render_template, request, redirect, url_for, flash
import psycopg2
from datetime import datetime, timedelta
import os
import pytz

# SEGURIDAD Y LOGIN
from flask_login import LoginManager, login_user, login_required, logout_user, current_user, UserMixin
from werkzeug.security import check_password_hash
from dotenv import load_dotenv

# --- 1. IMPORTACIÓN DE BLUEPRINTS ---
from rutas_admin import admin_bp          
from rutas_recorridos import usuario_bp   
from rutas_operador import operador_bp

load_dotenv()

app = Flask(__name__)
# SEGURIDAD: Solo usa el .env
app.secret_key = os.getenv("SECRET_KEY") 

# --- 2. REGISTRO DE BLUEPRINTS ---
app.register_blueprint(admin_bp)
app.register_blueprint(usuario_bp)
app.register_blueprint(operador_bp)

# --- 3. CONFIGURACIÓN LOGIN ---
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login' 

login_manager.login_message = "Por favor, inicie sesión para ingresar."
login_manager.login_message_category = "warning"

class User(UserMixin):
    def __init__(self, id, username, password, rol):
        self.id = id
        self.username = username
        self.password = password
        self.rol = rol

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
        print(f"Error conexión DB: {e}")
        return None

@login_manager.user_loader
def load_user(user_id):
    conn = obtener_conexion()
    if conn:
        cur = conn.cursor()
        cur.execute("SELECT id, username, password, rol FROM usuarios WHERE id = %s", (user_id,))
        user_data = cur.fetchone()
        cur.close()
        conn.close()
        if user_data:
            return User(user_data[0], user_data[1], user_data[2], user_data[3])
    return None



# RUTA PÚBLICA (PANTALLA TV) - LÓGICA CONTINUIDAD MADRUGADA


def obtener_datos_filtrados(tabla):
    conn = obtener_conexion()
    if not conn: return []
    
    cur = conn.cursor()
    
    # 2. DEFINIR ZONA HORARIA CHILE
    tz_chile = pytz.timezone('America/Santiago')
    ahora_chile = datetime.now(tz_chile)
    
    # 3. USAR LA HORA CHILENA PARA LOS CÁLCULOS
    fecha_hoy = ahora_chile.strftime('%Y-%m-%d')
    fecha_manana = (ahora_chile + timedelta(days=1)).strftime('%Y-%m-%d')
    
    # Consulta (La misma lógica de madrugada que ya aprobamos)
    sql = f"""
        SELECT id, hora, empresa_nombre, lugar, anden, fecha, estado 
        FROM {tabla}
        WHERE fecha = %s
           OR (fecha = %s AND hora <= '04:00:00')
        ORDER BY fecha ASC, hora ASC
    """
    
    cur.execute(sql, (fecha_hoy, fecha_manana))
    datos = cur.fetchall()
    
    cur.close()
    conn.close()
    return datos

@app.route('/pantalla')
def inicio():
    # Obtenemos los buses con la nueva lógica (Hoy + Madrugada siguiente)
    llegadas = obtener_datos_filtrados('import_llegadas')
    salidas = obtener_datos_filtrados('import_salidas')
    
    noticias = []
    conn = obtener_conexion()
    if conn:
        cur = conn.cursor()
        # Solo traemos las noticias donde activa = TRUE
        cur.execute("SELECT contenido FROM noticias WHERE activa = TRUE ORDER BY id DESC")
        noticias = [row[0] for row in cur.fetchall()]
        cur.close()
        conn.close()

    if not noticias:
        noticias = ["Bienvenido al Terminal de Buses de Coyhaique"]

    return render_template('index.html', 
                           llegadas=llegadas, 
                           salidas=salidas, 
                           noticias_db=noticias)


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        # 1. Recibimos 'rut' en lugar de 'username' del formulario HTML
        rut_ingresado = request.form['rut'] 
        clave = request.form['password']
        
        conn = obtener_conexion()
        if conn:
            cur = conn.cursor()
            
            # 2. Buscamos por RUT en el WHERE
            # (Seguimos trayendo el username en el SELECT para mostrarlo después)
            cur.execute("SELECT id, username, password, rol, activo, rut FROM usuarios WHERE rut = %s", (rut_ingresado,))
            user_data = cur.fetchone()
            cur.close()
            conn.close()

            if user_data:
                # user_data[4] es 'activo'
                if not user_data[4]: 
                    flash('Tu cuenta ha sido desactivada.', 'danger')
                    return render_template('login.html')

                # user_data[2] es la contraseña hash
                if check_password_hash(user_data[2], clave):
                    # Creamos la sesión. Nota: user_data[1] sigue siendo el NOMBRE para mostrar
                    user_obj = User(user_data[0], user_data[1], user_data[2], user_data[3])
                    login_user(user_obj)
                    
                    if user_obj.rol == 'operador':
                        return redirect(url_for('operador_bp.panel_operador'))
                    elif user_obj.rol == 'admin':
                        return redirect(url_for('admin_bp.admin_panel'))
                    else:
                        return redirect(url_for('usuario_bp.dashboard')) 
                else:
                    flash('RUT o contraseña incorrectos', 'danger')
            else:
                flash('RUT o contraseña incorrectos', 'danger')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Sesión cerrada.', 'success')
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True, port=5000)