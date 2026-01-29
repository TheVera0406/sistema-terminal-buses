from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for
from flask_login import login_required, current_user
import psycopg2
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

operador_bp = Blueprint('operador_bp', __name__)

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
        print(f"Error DB Operador: {e}")
        return None

# --- RUTA PRINCIPAL DEL PANEL ---
@operador_bp.route('/operador')
@login_required
def panel_operador():
    # 1. SEGURIDAD: Solo Admin y Operador pueden entrar
    if current_user.rol not in ['admin', 'operador']:
        flash("No tienes permiso para acceder al panel de operador.", "danger")
        return redirect(url_for('usuario_bp.dashboard'))

    conn = obtener_conexion()
    if not conn:
        flash("Error de conexión con la base de datos.", "danger")
        return redirect(url_for('usuario_bp.dashboard'))
        
    cur = conn.cursor()
    
    # 2. DEFINIR VENTANA DE TIEMPO
    # Mostramos lo que pasó hace 2 horas y lo que viene en las próximas 10 horas
    ahora = datetime.now()
    inicio_ventana = ahora - timedelta(hours=5)
    fin_ventana = ahora + timedelta(hours=10)

    # 3. FILTROS (Listas para llenar los selects del HTML)
    # Usamos UNION para sacar empresas y lugares de ambas tablas
    cur.execute("SELECT DISTINCT empresa_nombre FROM import_salidas UNION SELECT DISTINCT empresa_nombre FROM import_llegadas ORDER BY 1")
    lista_empresas = [fila[0] for fila in cur.fetchall()]

    cur.execute("SELECT DISTINCT lugar FROM import_salidas UNION SELECT DISTINCT lugar FROM import_llegadas ORDER BY 1")
    lista_lugares = [fila[0] for fila in cur.fetchall()]

    recorridos = []
    
    # 4. CONSULTA DE SALIDAS
    # Nota: (fecha + hora) funciona en PostgreSQL para crear un timestamp y comparar rangos
    query_salidas = """
        SELECT id, hora, empresa_nombre, lugar, anden, estado, fecha 
        FROM import_salidas 
        WHERE (fecha + hora) BETWEEN %s AND %s
        ORDER BY fecha ASC, hora ASC
    """
    cur.execute(query_salidas, (inicio_ventana, fin_ventana))
    for fila in cur.fetchall():
        recorridos.append({
            'id': fila[0],
            'hora': fila[1].strftime('%H:%M'), # Formato limpio HH:MM
            'empresa': fila[2],
            'lugar': fila[3],
            'anden': fila[4] if fila[4] else '?',
            'estado': fila[5] if fila[5] else 'Sin estado',
            'fecha': fila[6].strftime('%d/%m'),
            'tipo': 'salidas' # Identificador para saber a qué tabla actualizar luego
        })

    # 5. CONSULTA DE LLEGADAS
    query_llegadas = """
        SELECT id, hora, empresa_nombre, lugar, anden, estado, fecha 
        FROM import_llegadas 
        WHERE (fecha + hora) BETWEEN %s AND %s
        ORDER BY fecha ASC, hora ASC
    """
    cur.execute(query_llegadas, (inicio_ventana, fin_ventana))
    for fila in cur.fetchall():
        recorridos.append({
            'id': fila[0],
            'hora': fila[1].strftime('%H:%M'),
            'empresa': fila[2],
            'lugar': fila[3],
            'anden': fila[4] if fila[4] else '?',
            'estado': fila[5] if fila[5] else 'Sin estado',
            'fecha': fila[6].strftime('%d/%m'),
            'tipo': 'llegadas'
        })

    # 6. ORDENAR CRONOLÓGICAMENTE
    # Como unimos dos listas, hay que reordenarlas por hora para que se vean mezcladas correctamente
    recorridos.sort(key=lambda x: x['hora'])

    cur.close()
    conn.close()
    
    return render_template('operador.html', 
                           recorridos=recorridos, 
                           empresas=lista_empresas, 
                           lugares=lista_lugares,
                           usuario=current_user)

# --- RUTA PARA ACTUALIZAR ESTADO (API JSON) ---
@operador_bp.route('/actualizar_estado', methods=['POST'])
@login_required
def actualizar_estado():
    # Solo permitimos a admin y operador
    if current_user.rol not in ['admin', 'operador']:
        return jsonify({"status": "error", "message": "No autorizado"}), 403

    try:
        id_bus = request.form.get('id')
        tipo = request.form.get('tipo')      
        nuevo_estado = request.form.get('estado')
        
        if not id_bus or not tipo:
            return jsonify({"status": "error", "message": "Faltan datos"}), 400

        # Seleccionamos la tabla correcta según el tipo
        tabla = 'import_llegadas' if tipo == 'llegadas' else 'import_salidas'
        
        conn = obtener_conexion()
        cur = conn.cursor()
        
        # Actualizamos solo la columna 'estado'
        cur.execute(f"UPDATE {tabla} SET estado = %s WHERE id = %s", (nuevo_estado, id_bus))
        
        conn.commit()
        cur.close()
        conn.close()
        
        return jsonify({"status": "success"})
        
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500