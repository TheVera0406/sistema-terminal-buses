from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for
from flask_login import login_required, current_user
import psycopg2
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv
import pytz

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
    if current_user.rol not in ['admin', 'operador']:
        flash("No tienes permiso.", "danger")
        return redirect(url_for('usuario_bp.dashboard'))

    conn = obtener_conexion()
    if not conn:
        flash("Error de conexión.", "danger")
        return redirect(url_for('usuario_bp.dashboard'))
        
    cur = conn.cursor()
    
    # 2. DEFINIR ZONA HORARIA CHILE
    tz_chile = pytz.timezone('America/Santiago')
    ahora_chile = datetime.now(tz_chile)
    
    # 3. USAR HORA CHILENA COMO BASE
    fecha_hoy_str = ahora_chile.strftime('%Y-%m-%d')
    fecha_seleccionada_str = fecha_hoy_str 

    # Si es ADMIN y elige fecha (lógica igual, pero partiendo de la hora chilena correcta)
    if current_user.rol == 'admin':
        fecha_url = request.args.get('fecha')
        if fecha_url:
            fecha_seleccionada_str = fecha_url
            
    # Calcular día siguiente para la madrugada
    fecha_dt = datetime.strptime(fecha_seleccionada_str, '%Y-%m-%d')
    fecha_siguiente_dt = fecha_dt + timedelta(days=1)
    fecha_siguiente_str = fecha_siguiente_dt.strftime('%Y-%m-%d')

    # 3. LISTAS PARA FILTROS (Selects)
    cur.execute("SELECT DISTINCT empresa_nombre FROM import_salidas UNION SELECT DISTINCT empresa_nombre FROM import_llegadas ORDER BY 1")
    lista_empresas = [fila[0] for fila in cur.fetchall()]

    cur.execute("SELECT DISTINCT lugar FROM import_salidas UNION SELECT DISTINCT lugar FROM import_llegadas ORDER BY 1")
    lista_lugares = [fila[0] for fila in cur.fetchall()]

    recorridos = []
    
    # 4. CONSULTA SALIDAS (Día seleccionado COMPLETO + Madrugada siguiente hasta las 04:00)
    query_salidas = """
        SELECT id, hora, empresa_nombre, lugar, anden, estado, fecha 
        FROM import_salidas 
        WHERE fecha = %s 
           OR (fecha = %s AND hora <= '04:00:00')
        ORDER BY fecha ASC, hora ASC
    """
    # Pasamos dos parámetros: fecha elegida y fecha siguiente
    cur.execute(query_salidas, (fecha_seleccionada_str, fecha_siguiente_str))
    
    for fila in cur.fetchall():
        # Lógica visual: Si la fecha es distinta a la seleccionada, es madrugada
        es_madrugada = (str(fila[6]) == fecha_siguiente_str)
        hora_formato = fila[1].strftime('%H:%M')
        
        # Opcional: Agregar un indicativo visual en la hora (ej: "01:00 (+1)")
        # Por ahora lo dejamos limpio, pero el orden será correcto gracias al ORDER BY fecha, hora
        
        recorridos.append({
            'id': fila[0],
            'hora': hora_formato,
            'empresa': fila[2],
            'lugar': fila[3],
            'anden': fila[4] if fila[4] else '?',
            'estado': fila[5] if fila[5] else 'Sin estado',
            'fecha': fila[6].strftime('%d/%m'),
            'fecha_raw': fila[6], # Guardamos objeto fecha real para ordenar
            'tipo': 'salidas',
            'es_plus_uno': es_madrugada # Flag por si quieres usarlo en el HTML
        })

    # 5. CONSULTA LLEGADAS (Misma lógica)
    query_llegadas = """
        SELECT id, hora, empresa_nombre, lugar, anden, estado, fecha 
        FROM import_llegadas 
        WHERE fecha = %s 
           OR (fecha = %s AND hora <= '04:00:00')
        ORDER BY fecha ASC, hora ASC
    """
    cur.execute(query_llegadas, (fecha_seleccionada_str, fecha_siguiente_str))
    
    for fila in cur.fetchall():
        es_madrugada = (str(fila[6]) == fecha_siguiente_str)
        recorridos.append({
            'id': fila[0],
            'hora': fila[1].strftime('%H:%M'),
            'empresa': fila[2],
            'lugar': fila[3],
            'anden': fila[4] if fila[4] else '?',
            'estado': fila[5] if fila[5] else 'Sin estado',
            'fecha': fila[6].strftime('%d/%m'),
            'fecha_raw': fila[6],
            'tipo': 'llegadas',
            'es_plus_uno': es_madrugada
        })

    cur.close()
    conn.close()

    # 6. ORDENAR CRONOLÓGICAMENTE (Clave: Fecha primero, luego Hora)
    # Esto asegura que las 23:00 de HOY salgan antes que las 00:30 de MAÑANA
    recorridos.sort(key=lambda x: (x['fecha_raw'], x['hora']))
    
    return render_template('operador.html', 
                           recorridos=recorridos, 
                           empresas=lista_empresas, 
                           lugares=lista_lugares,
                           usuario=current_user,
                           fecha_seleccionada=fecha_seleccionada_str)

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
@operador_bp.route('/operador/verificar', methods=['POST'])
@login_required
def verificar_recorrido():
    # 1. Seguridad
    if current_user.rol not in ['admin', 'operador']:
        return jsonify({'status': 'error', 'message': 'No autorizado'}), 403

    try:
        # 2. Recibir datos del formulario
        recorrido_id = request.form.get('id_recorrido')
        tipo = request.form.get('tipo_recorrido') 
        patente_input = request.form.get('patente').strip().upper().replace("-", "")
        anden_real = request.form.get('anden_real').strip()
        observaciones = request.form.get('observaciones', '')
        
        # --- NUEVOS DATOS MANUALES ---
        fecha_manual = request.form.get('fecha_manual') # YYYY-MM-DD
        hora_manual = request.form.get('hora_manual')   # HH:MM
        
        if not fecha_manual or not hora_manual:
             return jsonify({'status': 'error', 'title': 'Datos Faltantes', 'message': 'Debe indicar Fecha y Hora.'}), 400
        # -----------------------------

        conn = obtener_conexion()
        cur = conn.cursor()

        # 3. Validaciones (Igual que antes)
        cur.execute("SELECT id, empresa FROM buses_permitidos WHERE patente = %s AND activa = TRUE", (patente_input,))
        bus_permitido = cur.fetchone()
        es_patente_valida = True if bus_permitido else False
        
        if tipo in ['llegada', 'llegadas']:
            tabla_db = 'import_llegadas'
        else:
            tabla_db = 'import_salidas'
        
        cur.execute(f"SELECT anden FROM {tabla_db} WHERE id = %s", (recorrido_id,))
        resultado_origen = cur.fetchone()
        
        if not resultado_origen:
             return jsonify({'status': 'error', 'title': 'Error', 'message': 'Recorrido no encontrado.'}), 404
             
        anden_programado = str(resultado_origen[0])
        es_anden_correcto = (str(anden_real) == anden_programado)

        # 4. GUARDAR EN BD (Usando las nuevas columnas)
# ... (código de inserción anterior igual) ...

        cur.execute("""
            INSERT INTO historial_verificaciones 
            (recorrido_id, tipo_recorrido, operador_id, patente_ingresada, anden_real, 
             es_patente_valida, es_anden_correcto, anden_programado, observaciones,
             fecha_manual, hora_manual)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (recorrido_id, tipo, current_user.id, patente_input, anden_real, 
              es_patente_valida, es_anden_correcto, anden_programado, observaciones,
              fecha_manual, hora_manual))
        
        # --- AGREGA ESTA LÍNEA NUEVA ---
        # Esto guarda el estado "En Andén" en la base de datos
        cur.execute(f"UPDATE {tabla_db} SET estado = 'En Andén' WHERE id = %s", (recorrido_id,))
        # -------------------------------
        
        conn.commit()
        cur.close()
        conn.close()


        # 5. Respuesta
        if not es_patente_valida:
            return jsonify({'status': 'error', 'title': '🚨 BUS NO AUTORIZADO', 'message': f'Patente {patente_input} no permitida.'})
        elif not es_anden_correcto:
            return jsonify({'status': 'warning', 'title': '⚠️ ANDÉN INCORRECTO', 'message': f'Andén {anden_real} incorrecto (Debía ser {anden_programado}).'})
        else:
            return jsonify({'status': 'success', 'title': '✅ REGISTRADO', 'message': 'Datos guardados correctamente.'})

    except Exception as e:
        print(f"Error Verificación: {e}")
        if 'conn' in locals() and conn: conn.rollback()
        return jsonify({'status': 'error', 'title': 'Error Técnico', 'message': str(e)}), 500
    
@operador_bp.route('/operador/registrar_extra', methods=['POST'])
@login_required
def registrar_extra():
    if current_user.rol not in ['admin', 'operador']:
        return jsonify({'status': 'error', 'message': 'No autorizado'}), 403

    # Datos recibidos
    patente = request.form.get('patente', '').strip().upper().replace("-", "")
    tipo = request.form.get('tipo') 
    anden = request.form.get('anden')
    
    # Aquí recibimos la observación tal cual la escribe el operador (puede estar vacía)
    observacion = request.form.get('observacion', '').strip()
    
    fecha_manual = request.form.get('fecha_manual')
    hora_manual = request.form.get('hora_manual')
    empresa_manual = request.form.get('empresa_manual', '').strip().upper()
    lugar_manual = request.form.get('lugar_manual', '').strip().upper()

    if not patente or not tipo or not anden or not fecha_manual or not hora_manual:
        return jsonify({'status': 'error', 'title': 'Faltan Datos', 'message': 'Complete los campos obligatorios.'})

    conn = obtener_conexion()
    cur = conn.cursor()

    try:
        # Validar Empresa (Mantenemos la lógica de corrección de nombre de empresa)
        cur.execute("SELECT empresa FROM buses_permitidos WHERE patente = %s", (patente,))
        res_patente = cur.fetchone()
        
        empresa_final = empresa_manual
        es_conocida = False

        if res_patente:
            empresa_final = res_patente[0]
            es_conocida = True
        else:
            if not empresa_final: empresa_final = "NO REGISTRADA"

        # --- CAMBIO AQUÍ ---
        # Eliminamos el bloque "if not observacion: ..."
        # Ahora, si 'observacion' está vacía, se guarda vacía en la base de datos.
        # -------------------

        cur.execute("""
            INSERT INTO historial_extras 
            (fecha, hora, patente, empresa, lugar, tipo_recorrido, anden, operador_id, observacion)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (fecha_manual, hora_manual, patente, empresa_final, lugar_manual, tipo, anden, current_user.id, observacion))
        
        conn.commit()
        
        titulo = "✅ EXTRA GUARDADO"
        mensaje = f"Bus {patente} ({empresa_final}) registrado."
        status = 'success' if es_conocida else 'warning'

        return jsonify({'status': status, 'title': titulo, 'message': mensaje})

    except Exception as e:
        conn.rollback()
        return jsonify({'status': 'error', 'title': 'Error', 'message': str(e)})
    finally:
        cur.close()
        conn.close()