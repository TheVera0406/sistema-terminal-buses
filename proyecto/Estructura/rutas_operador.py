from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for
from flask_login import login_required, current_user
import psycopg2
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

operador_bp = Blueprint('operador_bp', __name__)

def obtener_conexion():
    return psycopg2.connect(
        host=os.getenv("DB_HOST"),
        database=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASS"),
        port=os.getenv("DB_PORT", "5432")
    )

@operador_bp.route('/operador')
@login_required
def panel_operador():
    if current_user.rol not in ['admin', 'operador']:
        flash("No tienes permiso.", "danger")
        return redirect(url_for('login'))

    conn = obtener_conexion()
    cur = conn.cursor()
    
    # 1. DEFINIR VENTANA DE TIEMPO (-2h a +10h)
    ahora = datetime.now()
    fecha_hoy = ahora.date()
    inicio_ventana = (ahora - timedelta(hours=2)).time()
    fin_ventana = (ahora + timedelta(hours=10)).time() # Solicitado +10 horas

    # 2. OBTENER DATOS PARA LOS FILTROS DESPLEGABLES (Empresas y Lugares únicos)
    # Buscamos en ambas tablas para tener todas las opciones disponibles
    cur.execute("""
        SELECT DISTINCT empresa_nombre FROM import_salidas 
        UNION 
        SELECT DISTINCT empresa_nombre FROM import_llegadas 
        ORDER BY 1
    """)
    lista_empresas = [fila[0] for fila in cur.fetchall()]

    cur.execute("""
        SELECT DISTINCT lugar FROM import_salidas 
        UNION 
        SELECT DISTINCT lugar FROM import_llegadas 
        ORDER BY 1
    """)
    lista_lugares = [fila[0] for fila in cur.fetchall()]

    # 3. OBTENER RECORRIDOS (SALIDAS Y LLEGADAS) EN LA VENTANA DE TIEMPO
    recorridos = []
    
    # Consultamos Salidas
    query_salidas = """
        SELECT id, hora, empresa_nombre, lugar, anden, estado, fecha 
        FROM import_salidas 
        WHERE fecha = %s AND hora BETWEEN %s AND %s
        ORDER BY hora ASC
    """
    cur.execute(query_salidas, (fecha_hoy, inicio_ventana, fin_ventana))
    for fila in cur.fetchall():
        recorridos.append({
            'id': fila[0],
            'hora': fila[1].strftime('%H:%M'),
            'empresa': fila[2],
            'lugar': fila[3], # En salidas es Destino
            'anden': fila[4] if fila[4] else '?',
            'estado': fila[5] if fila[5] else 'Sin estado',
            'fecha': fila[6].strftime('%d/%m/%Y'),
            'tipo': 'salidas' # Etiqueta para el filtro
        })

    # Consultamos Llegadas
    query_llegadas = """
        SELECT id, hora, empresa_nombre, lugar, anden, estado, fecha 
        FROM import_llegadas 
        WHERE fecha = %s AND hora BETWEEN %s AND %s
        ORDER BY hora ASC
    """
    cur.execute(query_llegadas, (fecha_hoy, inicio_ventana, fin_ventana))
    for fila in cur.fetchall():
        recorridos.append({
            'id': fila[0],
            'hora': fila[1].strftime('%H:%M'),
            'empresa': fila[2],
            'lugar': fila[3], # En llegadas es Origen
            'anden': fila[4] if fila[4] else '?',
            'estado': fila[5] if fila[5] else 'Sin estado',
            'fecha': fila[6].strftime('%d/%m/%Y'),
            'tipo': 'llegadas' # Etiqueta para el filtro
        })

    # Ordenamos la lista combinada por hora para que se vea cronológico
    recorridos.sort(key=lambda x: x['hora'])

    cur.close()
    conn.close()
    
    return render_template('operador.html', 
                           recorridos=recorridos, 
                           empresas=lista_empresas, 
                           lugares=lista_lugares,
                           usuario=current_user)

@operador_bp.route('/actualizar_estado', methods=['POST'])
@login_required
def actualizar_estado():
    try:
        id_bus = request.form.get('id')
        tipo = request.form.get('tipo')      
        nuevo_estado = request.form.get('estado')
        
        if not id_bus or not tipo:
            return jsonify({"status": "error", "message": "Faltan datos"}), 400

        tabla = f'import_{tipo}' # import_salidas o import_llegadas
        
        conn = obtener_conexion()
        cur = conn.cursor()
        cur.execute(f"UPDATE {tabla} SET estado = %s WHERE id = %s", (nuevo_estado, id_bus))
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500