from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
import psycopg2
from datetime import datetime
import math
import os
import shutil
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
from psycopg2 import IntegrityError

import pandas as pd
from io import BytesIO
from flask import send_file

from manipulacion_datos.generar_salidas_llegadas import ejecutar_procesamiento_excel
from manipulacion_datos.insertar_datos import ejecutar_insercion_datos, obtener_id_empresa, obtener_id_lugar
from werkzeug.security import generate_password_hash

load_dotenv()

admin_bp = Blueprint('admin_bp', __name__)

def obtener_conexion_admin():
    try:
        return psycopg2.connect(
            host=os.getenv("DB_HOST"),
            database=os.getenv("DB_NAME"),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASS"),
            port=os.getenv("DB_PORT", "5432")
        )
    except Exception as e:
        print(f" Error DB Admin: {e}")
        return None

# --- PANEL PRINCIPAL ---
@admin_bp.route('/admin')
@login_required
def admin_panel():
    if current_user.rol != 'admin': return redirect(url_for('usuario_bp.dashboard'))

    # Fecha por defecto: HOY
    f_fecha = request.args.get('fecha', '')
    if not f_fecha:
        f_fecha = datetime.now().strftime('%Y-%m-%d')

    # Nuevo filtro: HORA
    f_hora = request.args.get('hora', '').strip()
    
    f_empresa = request.args.get('empresa', '')
    f_lugar = request.args.get('lugar', '')
    f_anden = request.args.get('anden', '')
    
    pagina = request.args.get('page', 1, type=int)
    por_pagina = 50 
    offset = (pagina - 1) * por_pagina

    conn = obtener_conexion_admin()
    if not conn:
        flash("Error de conexión a la base de datos", "danger")
        return redirect(url_for('login'))
    
    cur = conn.cursor()

    cur.execute("SELECT id, nombre FROM empresas ORDER BY nombre ASC")
    lista_empresas_full = cur.fetchall() 
    
    cur.execute("SELECT id, nombre FROM lugares ORDER BY nombre ASC")
    lista_lugares_full = cur.fetchall()

    # --- CAMBIO AQUÍ: Agregamos 'rut' al SELECT ---
    cur.execute("SELECT id, username, rol, activo, rut FROM usuarios ORDER BY id ASC") 
    lista_usuarios = cur.fetchall()

    lista_empresas = [e[1] for e in lista_empresas_full]
    lista_lugares = [l[1] for l in lista_lugares_full]

    cur.execute("SELECT id, contenido, fecha_creacion, activa FROM noticias ORDER BY id DESC")
    lista_noticias = cur.fetchall()

    condiciones = ["1=1"]
    params = []
    
    if f_fecha:
        condiciones.append("fecha = %s")
        params.append(f_fecha)
    
    # Lógica de filtro por hora
    if f_hora:
        condiciones.append("hora::text LIKE %s")
        params.append(f"{f_hora}%")

    if f_empresa:
        condiciones.append("empresa_nombre = %s")
        params.append(f_empresa)
    if f_lugar:
        condiciones.append("lugar = %s")
        params.append(f_lugar)
    if f_anden:
        condiciones.append("anden = %s")
        params.append(f_anden)

    where_clause = " AND ".join(condiciones)

    cur.execute(f"SELECT COUNT(*) FROM import_llegadas WHERE {where_clause}", params)
    total_llegadas = cur.fetchone()[0]
    cur.execute(f"SELECT id, hora, empresa_nombre, lugar, anden, fecha, 'llegadas' as tipo FROM import_llegadas WHERE {where_clause} ORDER BY hora ASC LIMIT %s OFFSET %s", (*params, por_pagina, offset))
    llegadas = cur.fetchall()

    cur.execute(f"SELECT COUNT(*) FROM import_salidas WHERE {where_clause}", params)
    total_salidas = cur.fetchone()[0]
    cur.execute(f"SELECT id, hora, empresa_nombre, lugar, anden, fecha, 'salidas' as tipo FROM import_salidas WHERE {where_clause} ORDER BY hora ASC LIMIT %s OFFSET %s", (*params, por_pagina, offset))
    salidas = cur.fetchall()

    # --- CAMBIO AQUÍ TAMBIÉN (Por si estaba duplicado) ---
    cur.execute("SELECT id, username, rol, activo, rut FROM usuarios ORDER BY id ASC")
    lista_usuarios = cur.fetchall()

    # Cargar lista de patentes
    cur.execute("SELECT id, patente, empresa FROM buses_permitidos ORDER BY empresa ASC, patente ASC")
    lista_patentes = cur.fetchall()

    cur.close()
    conn.close()

    total_paginas = math.ceil(max(total_llegadas, total_salidas) / por_pagina) if max(total_llegadas, total_salidas) > 0 else 1
    
    filtros = {'fecha': f_fecha, 'hora': f_hora, 'empresa': f_empresa, 'lugar': f_lugar, 'anden': f_anden}

    return render_template('admin.html', 
                           llegadas=llegadas, 
                           salidas=salidas, 
                           lista_noticias=lista_noticias,
                           pagina_actual=pagina, 
                           total_paginas=total_paginas,
                           lista_lugares=lista_lugares,
                           lista_empresas=lista_empresas,
                           filtros=filtros,
                           empresas_full=lista_empresas_full,
                           lugares_full=lista_lugares_full,
                           usuarios=lista_usuarios,
                           patentes=lista_patentes)

# --- NUEVA NOTICIA ---
@admin_bp.route('/admin/noticias/nueva', methods=['POST'])
@login_required
def nueva_noticia():
    if current_user.rol != 'admin': return redirect(url_for('usuario_bp.dashboard'))
    
    contenido = request.form.get('texto_noticia', '').strip()
    if contenido:
        conn = obtener_conexion_admin()
        cur = conn.cursor()
        cur.execute("INSERT INTO noticias (contenido) VALUES (%s)", (contenido,))
        conn.commit()
        cur.close()
        conn.close()
        flash('Noticia publicada.', 'success')
    return redirect(url_for('admin_bp.admin_panel'))

# --- ELIMINAR NOTICIA ---
@admin_bp.route('/admin/noticias/eliminar/<int:id>')
@login_required
def eliminar_noticia(id):
    if current_user.rol != 'admin': return redirect(url_for('usuario_bp.dashboard'))
    
    conn = obtener_conexion_admin()
    cur = conn.cursor()
    cur.execute("DELETE FROM noticias WHERE id = %s", (id,))
    conn.commit()
    cur.close()
    conn.close()
    flash('Noticia eliminada.', 'info')
    return redirect(url_for('admin_bp.admin_panel'))

# --- IMPORTAR EXCEL ---
@admin_bp.route('/admin/importar', methods=['POST'])
@login_required
def importar_excel():
    if current_user.rol != 'admin': return redirect(url_for('usuario_bp.dashboard'))
    
    archivos = request.files.getlist('file')
    carpeta_temp = os.path.join(os.getcwd(), 'temp_uploads')
    if not os.path.exists(carpeta_temp): os.makedirs(carpeta_temp)
    
    try:
        archivos_validos = 0
        nombres_invalidos = []

        for archivo in archivos:
            if not archivo.filename: continue
            
            if not archivo.filename.endswith('.xlsx'):
                flash(f"Error: '{archivo.filename}' no es un Excel (.xlsx). Ignorado.", "danger")
                continue
            
            nombre_mayus = archivo.filename.upper()
            if "SALIDA" not in nombre_mayus and "LLEGADA" not in nombre_mayus:
                nombres_invalidos.append(archivo.filename)
                continue

            archivo.save(os.path.join(carpeta_temp, secure_filename(archivo.filename)))
            archivos_validos += 1
        
        if nombres_invalidos:
            flash(f"Archivos con nombre incorrecto (falta 'SALIDAS' o 'LLEGADAS'): {', '.join(nombres_invalidos)}", "danger")

        if archivos_validos > 0:
            exito_csv, mensajes_csv = ejecutar_procesamiento_excel(carpeta_temp)
            
            # Mostramos errores de CSV (formato, fecha no encontrada)
            for msg in mensajes_csv:
                flash(msg, "danger")

            if exito_csv:
                exito_db, mensajes_db = ejecutar_insercion_datos(carpeta_temp)
                
                # --- NUEVA LÓGICA SIN EMOJIS ---
                for msg in mensajes_db:
                    if "Advertencia" in msg:
                        flash(msg, "warning")
                    elif "Éxito" in msg: 
                        flash(msg, "success")
                    else:
                        flash(msg, "danger")
                # -------------------------------

                # --- NUEVO: SINCRONIZACIÓN AUTOMÁTICA TRAS IMPORTACIÓN ---
                if exito_db:
                    try:
                        conn_sync = obtener_conexion_admin()
                        cur_sync = conn_sync.cursor()
                        
                        # 1. Insertar empresas nuevas faltantes
                        cur_sync.execute("""
                            INSERT INTO empresas (nombre)
                            SELECT DISTINCT empresa_nombre FROM import_llegadas 
                            WHERE empresa_nombre IS NOT NULL AND empresa_nombre != ''
                            AND empresa_nombre NOT IN (SELECT nombre FROM empresas);
                        """)
                        cur_sync.execute("""
                            INSERT INTO empresas (nombre)
                            SELECT DISTINCT empresa_nombre FROM import_salidas 
                            WHERE empresa_nombre IS NOT NULL AND empresa_nombre != ''
                            AND empresa_nombre NOT IN (SELECT nombre FROM empresas);
                        """)
                        
                        # 2. Insertar lugares nuevos faltantes
                        cur_sync.execute("""
                            INSERT INTO lugares (nombre)
                            SELECT DISTINCT lugar FROM import_llegadas 
                            WHERE lugar IS NOT NULL AND lugar != '' 
                            AND lugar NOT IN (SELECT nombre FROM lugares);
                        """)
                        cur_sync.execute("""
                            INSERT INTO lugares (nombre)
                            SELECT DISTINCT lugar FROM import_salidas 
                            WHERE lugar IS NOT NULL AND lugar != ''
                            AND lugar NOT IN (SELECT nombre FROM lugares);
                        """)

                        conn_sync.commit()
                        cur_sync.close()
                        conn_sync.close()
                        flash("Empresas y Lugares nuevos detectados en el Excel han sido registrados.", "info")
                    except Exception as e:
                        print(f"Error en sincronización automática: {e}")
                # ---------------------------------------------------------

            else:
                flash("No se pudieron extraer datos válidos de los archivos.", "danger")
        else:
            flash('No se cargaron archivos válidos.', 'warning')
            
    except Exception as e:
        flash(f'Error Crítico: {str(e)}', 'danger')
    finally:
        if os.path.exists(carpeta_temp): shutil.rmtree(carpeta_temp)
        
    return redirect(url_for('admin_bp.admin_panel'))


# --- ELIMINAR UNO SOLO ---
@admin_bp.route('/admin/eliminar/<tipo>/<int:id>')
@login_required
def eliminar(tipo, id):
    if current_user.rol != 'admin': return redirect(url_for('usuario_bp.dashboard'))
    
    tabla = "import_llegadas" if tipo == "llegada" else "import_salidas"
    conn = obtener_conexion_admin()
    cur = conn.cursor()
    cur.execute(f"DELETE FROM {tabla} WHERE id = %s", (id,))
    conn.commit()
    cur.close()
    conn.close()
    flash('Registro eliminado.', 'info')
    return redirect(url_for('admin_bp.admin_panel'))

# --- EDITAR O CREAR (MODAL) ---
@admin_bp.route('/admin/editar', methods=['POST'])
@login_required
def editar_registro():
    if current_user.rol != 'admin': return redirect(url_for('usuario_bp.dashboard'))

    id_reg = request.form.get('id') 
    tipo = request.form.get('tipo') 
    tabla = 'import_llegadas' if tipo == 'llegada' else 'import_salidas'
    
    # Datos del formulario
    fecha = request.form.get('fecha')
    hora = request.form.get('hora')
    empresa = request.form.get('empresa')
    lugar = request.form.get('lugar')
    anden = request.form.get('anden')

    conn = obtener_conexion_admin()
    cur = conn.cursor()

    try:
        # --- NUEVO: SINCRONIZACIÓN AUTOMÁTICA ---
        # Si la empresa no existe en la tabla maestra, la creamos
        if empresa:
            cur.execute("SELECT id FROM empresas WHERE nombre = %s", (empresa,))
            if not cur.fetchone():
                cur.execute("INSERT INTO empresas (nombre) VALUES (%s)", (empresa,))
                flash(f"Nueva empresa '{empresa}' registrada en el sistema.", "info")
        
        # Si el lugar no existe en la tabla maestra, lo creamos
        if lugar:
             cur.execute("SELECT id FROM lugares WHERE nombre = %s", (lugar,))
             if not cur.fetchone():
                 cur.execute("INSERT INTO lugares (nombre) VALUES (%s)", (lugar,))
        # ----------------------------------------

        if id_reg == '0':
            cur.execute(f"""
                INSERT INTO {tabla} (fecha, hora, empresa_nombre, lugar, anden, estado)
                VALUES (%s, %s, %s, %s, %s, 'Programado')
            """, (fecha, hora, empresa, lugar, anden))
            flash('Nuevo recorrido creado exitosamente.', 'success')
        else:
            cur.execute(f"""
                UPDATE {tabla} 
                SET fecha=%s, hora=%s, empresa_nombre=%s, lugar=%s, anden=%s 
                WHERE id=%s
            """, (fecha, hora, empresa, lugar, anden, id_reg))
            flash('Registro actualizado.', 'success')

        conn.commit()

    except Exception as e:
        conn.rollback()
        print(f"Error SQL: {e}") 
        flash(f'Error al guardar: {e}', 'danger')
    finally:
        cur.close()
        conn.close()

    return redirect(url_for('admin_bp.admin_panel'))


# --- EDITAR TEXTO DE NOTICIA ---
@admin_bp.route('/admin/noticias/editar', methods=['POST'])
@login_required
def editar_noticia_texto():
    if current_user.rol != 'admin': return redirect(url_for('usuario_bp.dashboard'))
    
    id_noticia = request.form.get('id_noticia')
    nuevo_contenido = request.form.get('texto_noticia_edit').strip()
    
    if id_noticia and nuevo_contenido:
        conn = obtener_conexion_admin()
        cur = conn.cursor()
        cur.execute("UPDATE noticias SET contenido = %s WHERE id = %s", (nuevo_contenido, id_noticia))
        conn.commit()
        cur.close()
        conn.close()
        flash('Noticia actualizada correctamente.', 'success')
    
    return redirect(url_for('admin_bp.admin_panel'))

# --- CAMBIAR ESTADO (CHECK) ---
@admin_bp.route('/admin/noticias/estado/<int:id>', methods=['POST'])
@login_required
def cambiar_estado_noticia(id):
    if current_user.rol != 'admin': return jsonify({'status': 'error'}), 403
    
    data = request.get_json()
    nuevo_estado = data.get('activa') # Esto será True o False
    
    conn = obtener_conexion_admin()
    cur = conn.cursor()
    cur.execute("UPDATE noticias SET activa = %s WHERE id = %s", (nuevo_estado, id))
    conn.commit()
    cur.close()
    conn.close()
    
    return jsonify({'status': 'success'})

# ==========================================
# GESTIÓN DE DATOS MAESTROS (EMPRESAS / LUGARES)
# ==========================================

@admin_bp.route('/admin/maestros/agregar', methods=['POST'])
@login_required
def agregar_maestro():
    if current_user.rol != 'admin': return redirect(url_for('usuario_bp.dashboard'))

    tipo = request.form.get('tipo') # 'empresa' o 'lugar'
    nombre = request.form.get('nombre').strip().upper() # Guardamos en mayúsculas para ordenar

    if not nombre:
        flash("El nombre no puede estar vacío.", "warning")
        return redirect(url_for('admin_bp.admin_panel'))

    conn = obtener_conexion_admin()
    cur = conn.cursor()
    
    tabla = "empresas" if tipo == "empresa" else "lugares"
    
    try:
        cur.execute(f"INSERT INTO {tabla} (nombre) VALUES (%s)", (nombre,))
        conn.commit()
        flash(f"{tipo.capitalize()} '{nombre}' agregada correctamente.", "success")
    except IntegrityError:
        conn.rollback()
        flash(f"Error: Ya existe {tipo} con ese nombre.", "danger")
    except Exception as e:
        conn.rollback()
        flash(f"Error desconocido: {e}", "danger")
    finally:
        cur.close()
        conn.close()

    return redirect(url_for('admin_bp.admin_panel'))


@admin_bp.route('/admin/maestros/eliminar', methods=['POST'])
@login_required
def eliminar_maestro():
    if current_user.rol != 'admin': return redirect(url_for('usuario_bp.dashboard'))

    tipo = request.form.get('tipo') # 'empresa' o 'lugar'
    id_dato = request.form.get('id')

    if not id_dato:
        flash("Error: Identificador no válido.", "danger")
        return redirect(url_for('admin_bp.admin_panel'))

    conn = obtener_conexion_admin()
    cur = conn.cursor()
    
    # Definimos en qué tabla buscar el nombre
    tabla_maestra = "empresas" if tipo == "empresa" else "lugares"
    
    try:
        # --- PASO 1: OBTENER EL NOMBRE REAL ---
        # Primero averiguamos cómo se llama la empresa/lugar que quieres borrar
        cur.execute(f"SELECT nombre FROM {tabla_maestra} WHERE id = %s", (id_dato,))
        resultado = cur.fetchone()
        
        if not resultado:
            flash(f"Error: No se encontró el registro en {tabla_maestra}.", "warning")
            return redirect(url_for('admin_bp.admin_panel'))
            
        nombre_real = resultado[0] # Ej: "Empresa Prueba"

        # --- PASO 2: VERIFICAR SI ESE NOMBRE SE ESTÁ USANDO ---
        # Buscamos en las tablas de recorridos por el TEXTO, no por el ID.
        
        if tipo == "empresa":
            # Verificamos columna 'empresa_nombre'
            cur.execute("SELECT COUNT(*) FROM import_salidas WHERE empresa_nombre = %s", (nombre_real,))
            count_salidas = cur.fetchone()[0]
            
            cur.execute("SELECT COUNT(*) FROM import_llegadas WHERE empresa_nombre = %s", (nombre_real,))
            count_llegadas = cur.fetchone()[0]
            
        else: # es lugar
            # Verificamos columna 'lugar'
            cur.execute("SELECT COUNT(*) FROM import_salidas WHERE lugar = %s", (nombre_real,))
            count_salidas = cur.fetchone()[0]
            
            cur.execute("SELECT COUNT(*) FROM import_llegadas WHERE lugar = %s", (nombre_real,))
            count_llegadas = cur.fetchone()[0]

        # --- PASO 3: DECIDIR SI BORRAMOS ---
        total_usos = count_salidas + count_llegadas

        if total_usos > 0:
            # Si se está usando, prohibimos borrar
            flash(f"NO SE PUEDE BORRAR: '{nombre_real}' se está usando en {total_usos} recorridos. Debes eliminarlos primero.", "danger")
            conn.rollback()
        else:
            # Si nadie lo usa, procedemos a borrar usando el ID
            cur.execute(f"DELETE FROM {tabla_maestra} WHERE id = %s", (id_dato,))
            conn.commit()
            flash(f"'{nombre_real}' eliminado correctamente.", "success")

    except Exception as e:
        conn.rollback()
        flash(f"Error técnico al eliminar: {e}", "danger")
    finally:
        cur.close()
        conn.close()

    return redirect(url_for('admin_bp.admin_panel'))


# GESTIÓN DE USUARIOS (CRUD)
# --- CREAR USUARIO ---
@admin_bp.route('/admin/usuarios/crear', methods=['POST'])
@login_required
def crear_usuario_web():
    if current_user.rol != 'admin': return redirect(url_for('usuario_bp.dashboard'))
    
    # 1. Recibimos los datos (incluyendo el RUT)
    username = request.form.get('nuevo_username').strip()
    rut = request.form.get('rut').strip()  # <--- NUEVO
    password = request.form.get('nuevo_password').strip()
    rol = request.form.get('nuevo_rol')

    if not username or not password or not rol or not rut:
        flash("Faltan datos para crear el usuario.", "warning")
        return redirect(url_for('admin_bp.admin_panel'))

    # encriptación
    hashed_password = generate_password_hash(password)

    conn = obtener_conexion_admin()
    cur = conn.cursor()
    try:
        # 2. Modificamos el INSERT para incluir el rut
        cur.execute("INSERT INTO usuarios (username, rut, password, rol, activo) VALUES (%s, %s, %s, %s, TRUE)", 
                    (username, rut, hashed_password, rol))
        conn.commit()
        flash(f"Usuario '{username}' (RUT: {rut}) creado exitosamente.", "success")
    
    except IntegrityError:
        conn.rollback()
        flash(f"Error: El RUT '{rut}' o el usuario ya existen.", "danger")
    except Exception as e:
        conn.rollback()
        flash(f"Error desconocido: {e}", "danger")
    finally:
        cur.close()
        conn.close()
    
    return redirect(url_for('admin_bp.admin_panel'))

# --- ELIMINAR USUARIO ---
@admin_bp.route('/admin/usuarios/eliminar/<int:id_user>', methods=['POST'])
@login_required
def eliminar_usuario(id_user):
    if current_user.rol != 'admin': return redirect(url_for('usuario_bp.dashboard'))
    
    # Seguridad: Evitar que el admin se borre a sí mismo mientras está conectado
    if id_user == current_user.id:
        flash("No puedes eliminar tu propia cuenta mientras estás en sesión.", "danger")
        return redirect(url_for('admin_bp.admin_panel'))

    conn = obtener_conexion_admin()
    cur = conn.cursor()
    try:
        cur.execute("DELETE FROM usuarios WHERE id = %s", (id_user,))
        conn.commit()
        flash("Usuario eliminado correctamente.", "success")
    except Exception as e:
        conn.rollback()
        flash(f"Error al eliminar: {e}", "danger")
    finally:
        cur.close()
        conn.close()
        
    return redirect(url_for('admin_bp.admin_panel'))

# --- EDITAR USUARIO ---
# --- EDITAR USUARIO (CORREGIDO) ---
@admin_bp.route('/admin/usuarios/editar', methods=['POST'])
@login_required
def editar_usuario():
    if current_user.rol != 'admin': return redirect(url_for('usuario_bp.dashboard'))
    
    # 1. CORRECCIÓN DE NOMBRES (Deben coincidir con el name="" del HTML)
    id_user = request.form.get('id_usuario') # HTML name="id_usuario"
    
    # Usamos (..., '') para evitar el error 'NoneType' si el campo no llega
    username = request.form.get('username', '').strip() # HTML name="username"
    
    # Limpieza de RUT (Igual que en crear)
    rut_raw = request.form.get('rut', '').strip()
    rut = rut_raw.replace('.', '').upper()
    
    # Manejo seguro de contraseña (puede venir vacía si no se quiere cambiar)
    password = request.form.get('password', '').strip() # HTML name="password"
    
    rol = request.form.get('rol') # HTML name="rol"

    conn = obtener_conexion_admin()
    cur = conn.cursor()
    
    try:
        if password:
            # Si escribieron algo en password, la actualizamos
            hashed_password = generate_password_hash(password)
            cur.execute("""
                UPDATE usuarios SET username=%s, rut=%s, password=%s, rol=%s WHERE id=%s
            """, (username, rut, hashed_password, rol, id_user))
            flash(f"Usuario actualizado correctamente (con nueva contraseña).", "success")
        else:
            # Si la password está vacía, SOLO actualizamos datos, mantenemos la clave vieja
            cur.execute("""
                UPDATE usuarios SET username=%s, rut=%s, rol=%s WHERE id=%s
            """, (username, rut, rol, id_user))
            flash(f"Usuario actualizado correctamente.", "success")
        
        conn.commit()
    except Exception as e:
        conn.rollback()
        flash(f"Error al editar (posible RUT duplicado): {e}", "danger")
    finally:
        cur.close()
        conn.close()

    return redirect(url_for('admin_bp.admin_panel'))


# GESTIÓN DE PATENTES

@admin_bp.route('/admin/flota/agregar', methods=['POST'])
@login_required
def agregar_patente():
    if current_user.rol != 'admin': return redirect(url_for('usuario_bp.dashboard'))

    patente = request.form.get('patente').strip().upper().replace("-", "") # Guardamos sin guiones
    empresa = request.form.get('empresa')

    if not patente:
        flash("La patente es obligatoria.", "warning")
        return redirect(url_for('admin_bp.admin_panel'))

    conn = obtener_conexion_admin()
    cur = conn.cursor()
    try:
        cur.execute("INSERT INTO buses_permitidos (patente, empresa) VALUES (%s, %s)", (patente, empresa))
        conn.commit()
        flash(f"Patente {patente} agregada a la lista permitida.", "success")
    except IntegrityError:
        conn.rollback()
        flash(f"Error: La patente {patente} ya está registrada.", "danger")
    except Exception as e:
        conn.rollback()
        flash(f"Error: {e}", "danger")
    finally:
        cur.close()
        conn.close()
    
    return redirect(url_for('admin_bp.admin_panel'))


@admin_bp.route('/admin/flota/eliminar', methods=['POST'])
@login_required
def eliminar_patente():
    if current_user.rol != 'admin': return redirect(url_for('usuario_bp.dashboard'))

    id_patente = request.form.get('id')
    
    conn = obtener_conexion_admin()
    cur = conn.cursor()
    try:
        cur.execute("DELETE FROM buses_permitidos WHERE id = %s", (id_patente,))
        conn.commit()
        flash("Patente eliminada de la lista permitida.", "success")
    except Exception as e:
        conn.rollback()
        flash(f"Error al eliminar: {e}", "danger")
    finally:
        cur.close()
        conn.close()
        
    return redirect(url_for('admin_bp.admin_panel'))



# REPORTE DE VERIFICACIONES (EXCEL)

@admin_bp.route('/admin/reportes/verificaciones', methods=['POST'])
@login_required
def descargar_reporte_verificaciones():
    if current_user.rol != 'admin': return redirect(url_for('usuario_bp.dashboard'))

    fecha_reporte = request.form.get('fecha_reporte')
    
    conn = obtener_conexion_admin()
    cur = conn.cursor()

    try:
        # CONSULTA SQL MAESTRA
        # Unimos tabla historial con usuarios para saber QUIÉN hizo la revisión
        sql = """
            SELECT 
                h.id,
                u.username as operador,
                h.tipo_recorrido,
                h.patente_ingresada,
                CASE WHEN h.es_patente_valida THEN 'SI' ELSE 'NO' END as patente_ok,
                h.anden_programado,
                h.anden_real,
                CASE WHEN h.es_anden_correcto THEN 'SI' ELSE 'NO' END as anden_ok,
                TO_CHAR(h.fecha_manual, 'DD/MM/YYYY') as fecha_ingreso,
                TO_CHAR(h.hora_manual, 'HH24:MI') as hora_ingreso,
                h.observaciones
            FROM historial_verificaciones h
            JOIN usuarios u ON h.operador_id = u.id
            WHERE h.fecha_manual = %s 
            ORDER BY h.fecha_manual DESC, h.hora_manual DESC
        """
        
        # Usamos Pandas para leer directo de la DB
        df = pd.read_sql_query(sql, conn, params=(fecha_reporte,))
        
        if df.empty:
            flash(f"No hay verificaciones registradas para el día {fecha_reporte}.", "warning")
            return redirect(url_for('admin_bp.admin_panel'))

        # RENOMBRAMOS COLUMNAS (Para que el Excel se vea bonito)
        df.columns = ['ID', 'OPERADOR', 'TIPO', 'PATENTE', '¿PATENTE OK?', 
                      'ANDÉN PROG.', 'ANDÉN REAL', '¿ANDÉN OK?', 
                      'FECHA INGRESO', 'HORA INGRESO', 'OBSERVACIONES']

        # GENERAR EXCEL EN MEMORIA (Sin guardar archivo en disco)
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Verificaciones')
            
            # Ajuste automático de ancho de columnas (Opcional, estético)
            worksheet = writer.sheets['Verificaciones']
            for column_cells in worksheet.columns:
                length = max(len(str(cell.value)) for cell in column_cells)
                worksheet.column_dimensions[column_cells[0].column_letter].width = length + 2

        output.seek(0)
        
        # NOMBRE DEL ARCHIVO
        nombre_archivo = f"Reporte_Verificaciones_{fecha_reporte}.xlsx"

        return send_file(
            output,
            as_attachment=True,
            download_name=nombre_archivo,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )

    except Exception as e:
        flash(f"Error al generar reporte: {e}", "danger")
        return redirect(url_for('admin_bp.admin_panel'))
    finally:
        cur.close()
        conn.close()


# CAMBIAR ESTADO USUARIO (SWITCH)

@admin_bp.route('/admin/usuarios/estado', methods=['POST'])
@login_required
def cambiar_estado_usuario():
    if current_user.rol != 'admin': 
        return jsonify({'status': 'error', 'message': 'No autorizado'}), 403

    data = request.get_json()
    usuario_id = data.get('id')
    nuevo_estado = data.get('activo') # True o False

    # Evitar que el admin se desactive a sí mismo por error
    if int(usuario_id) == current_user.id:
        return jsonify({'status': 'error', 'message': 'No puedes desactivar tu propia cuenta.'})

    conn = obtener_conexion_admin()
    cur = conn.cursor()
    try:
        cur.execute("UPDATE usuarios SET activo = %s WHERE id = %s", (nuevo_estado, usuario_id))
        conn.commit()
        return jsonify({'status': 'success'})
    except Exception as e:
        conn.rollback()
        return jsonify({'status': 'error', 'message': str(e)})
    finally:
        cur.close()
        conn.close()

# --- REPORTE OFICIAL (Corregido para tablas separadas) ---
@admin_bp.route('/admin/exportar_excel_rango', methods=['POST'])
@login_required
def exportar_excel_rango():
    if current_user.rol != 'admin': return redirect(url_for('login'))

    f_inicio = request.form['fecha_inicio']
    f_fin = request.form['fecha_fin']

    conn = obtener_conexion_admin()
    cur = conn.cursor()

    # LEFT JOIN condicionales a 'import_salidas' y 'import_llegadas'
    query = """
        SELECT 
            h.id,
            TO_CHAR(h.fecha_manual, 'YYYY-MM-DD') as fecha,
            TO_CHAR(h.hora_manual, 'HH24:MI') as hora,
            
            -- Buscamos el lugar en salidas o llegadas según corresponda
            COALESCE(s.lugar, l.lugar, 'No Especificado') as lugar,
            
            -- Buscamos la empresa programada en salidas o llegadas
            COALESCE(s.empresa_nombre, l.empresa_nombre, 'Bus Extra / No Prog.') as empresa_responsable,
            
            h.anden_real,
            u.username,
            h.patente_ingresada,
            CASE WHEN h.es_patente_valida THEN 'SI' ELSE 'NO' END as placa_valida,
            h.observaciones,
            COALESCE(bp.empresa, 'No Registrada') as empresa_duena
            
        FROM historial_verificaciones h
        
        -- UNIMOS CON SALIDAS (Solo si el tipo es 'salidas')
        LEFT JOIN import_salidas s ON h.recorrido_id = s.id AND h.tipo_recorrido = 'salidas'
        
        -- UNIMOS CON LLEGADAS (Solo si el tipo es 'llegadas')
        LEFT JOIN import_llegadas l ON h.recorrido_id = l.id AND h.tipo_recorrido = 'llegadas'
        
        JOIN usuarios u ON h.operador_id = u.id
        LEFT JOIN buses_permitidos bp ON h.patente_ingresada = bp.patente
        
        WHERE h.fecha_manual BETWEEN %s AND %s
        ORDER BY h.fecha_manual DESC, h.hora_manual DESC
    """

    cur.execute(query, (f_inicio, f_fin))
    datos = cur.fetchall()
    conn.close()

    # 2. DEFINIR COLUMNAS
    columnas = [
        'ID', 
        'Fecha', 
        'Hora', 
        'Lugar', 
        'Empresa (Itinerario)', 
        'Andén', 
        'Operador', 
        'Placa', 
        '¿Placa Válida?', 
        'Observación',
        'Empresa (Dueña Bus)'
    ]

    df_main = pd.DataFrame(datos, columns=columnas)

    if df_main.empty:
        flash(f"No hay registros oficiales entre {f_inicio} y {f_fin}.", "warning")
        return redirect(url_for('admin_bp.admin_panel'))

    # 3. GENERAR EL RESUMEN
    df_resumen = df_main.groupby(['Placa', 'Empresa (Dueña Bus)', '¿Placa Válida?']).size().reset_index(name='Cantidad_Viajes')
    df_resumen = df_resumen.sort_values(by='Cantidad_Viajes', ascending=False)
    
    # Renombrar columna para coincidir con el otro reporte
    df_resumen = df_resumen.rename(columns={'Empresa (Dueña Bus)': 'Empresa'})

    # 4. GENERAR EXCEL
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        
        # HOJA 1: DETALLE
        df_main.to_excel(writer, sheet_name='Detalle_Oficial', index=False)
        
        # HOJA 2: RESUMEN
        df_resumen.to_excel(writer, sheet_name='Resumen_Por_Placa', index=False)

        # --- ESTILOS ---
        workbook = writer.book
        fmt_head_blue = workbook.add_format({'bold': True, 'bg_color': '#002b3f', 'font_color': 'white', 'border': 1, 'align': 'center'})
        fmt_center = workbook.add_format({'align': 'center', 'border': 1})

        # Estilo Hoja 1
        worksheet1 = writer.sheets['Detalle_Oficial']
        for i, col in enumerate(df_main.columns):
            worksheet1.write(0, i, col, fmt_head_blue)
            worksheet1.set_column(i, i, 15, fmt_center)

        # Estilo Hoja 2
        worksheet2 = writer.sheets['Resumen_Por_Placa']
        for i, col in enumerate(df_resumen.columns):
            worksheet2.write(0, i, col, fmt_head_blue)
            worksheet2.set_column(i, i, 20, fmt_center)

    output.seek(0)
    
    return send_file(
        output,
        as_attachment=True,
        download_name=f"Reporte_OFICIAL_{f_inicio}_al_{f_fin}.xlsx",
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
# --- REPORTE DE EXTRAS ---
@admin_bp.route('/admin/reporte_extras_rango', methods=['POST'])
@login_required
def reporte_extras_rango():
    if current_user.rol != 'admin': return redirect(url_for('login'))

    f_inicio = request.form['fecha_inicio']
    f_fin = request.form['fecha_fin']

    conn = obtener_conexion_admin()
    cur = conn.cursor()


    # 1. Hacemos LEFT JOIN con 'buses_permitidos' para ver si la placa es válida
    query = """
        SELECT 
            h.id,
            h.fecha,
            h.hora,
            COALESCE(h.lugar, '') as lugar,  -- AHORA SÍ TRAEMOS EL LUGAR
            h.empresa,
            h.anden,
            u.username as operador,
            h.patente,
            CASE WHEN bp.patente IS NOT NULL THEN 'SI' ELSE 'NO' END as placa_valida,
            h.observacion
        FROM historial_extras h
        LEFT JOIN usuarios u ON h.operador_id = u.id
        LEFT JOIN buses_permitidos bp ON h.patente = bp.patente
        WHERE h.fecha BETWEEN %s AND %s
        ORDER BY h.fecha DESC, h.hora DESC
    """
    
    cur.execute(query, (f_inicio, f_fin))
    datos = cur.fetchall()
    conn.close()

    # NOMBRES
    columnas = [
        'ID', 
        'Fecha', 
        'Hora', 
        'Lugar', 
        'Empresa', 
        'Andén', 
        'Operador', 
        'Placa', 
        '¿Placa Válida?', 
        'Observación'
    ]
    
    df = pd.DataFrame(datos, columns=columnas)

    if df.empty:
        flash(f"No se encontraron registros extra entre {f_inicio} y {f_fin}.", "warning")
        return redirect(url_for('admin_bp.admin_panel'))

    # GENERAR TABLA RESUMEN (Conteos)
    resumen = df.groupby(['Placa', 'Empresa', '¿Placa Válida?']).size().reset_index(name='Cantidad_Viajes')
    resumen = resumen.sort_values(by='Cantidad_Viajes', ascending=False)

    # GENERAR ARCHIVO EXCEL
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        
        # 1. Hoja Principal con tus columnas
        df.to_excel(writer, sheet_name='Detalle_Extras', index=False)
        
        # 2. Hoja Resumen
        resumen.to_excel(writer, sheet_name='Resumen_Por_Placa', index=False)

        # --- ESTILOS VISUALES ---
        workbook = writer.book
        # Estilo Naranja (Para diferenciar que es un reporte EXTRA)
        fmt_head = workbook.add_format({'bold': True, 'bg_color': '#fd7e14', 'font_color': 'white', 'border': 1, 'align': 'center'})
        fmt_center = workbook.add_format({'align': 'center', 'border': 1})
        
        worksheet = writer.sheets['Detalle_Extras']
        
        # Ajustar anchos de columna y centrar
        anchos = [10, 15, 10, 20, 25, 10, 20, 15, 15, 40] # Anchos aproximados para tus columnas
        for i, ancho in enumerate(anchos):
            worksheet.set_column(i, i, ancho, fmt_center)
            # Reescribir encabezado con formato
            worksheet.write(0, i, columnas[i], fmt_head)

        # Estilo para la hoja resumen
        worksheet_res = writer.sheets['Resumen_Por_Placa']
        for i, col in enumerate(resumen.columns):
            worksheet_res.write(0, i, col, fmt_head)
            worksheet_res.set_column(i, i, 20, fmt_center)

    output.seek(0)
    
    return send_file(
        output, 
        as_attachment=True, 
        download_name=f"Reporte_EXTRAS_{f_inicio}_al_{f_fin}.xlsx",
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )



