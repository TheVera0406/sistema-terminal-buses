from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
import psycopg2
from datetime import datetime
import math
import os
import shutil
from werkzeug.utils import secure_filename

from dotenv import load_dotenv

# --- IMPORTACIÓN DE MÓDULOS PERSONALIZADOS ---
from manipulacion_datos.generar_salidas_llegadas import ejecutar_procesamiento_excel
from manipulacion_datos.insertar_datos import ejecutar_insercion_datos, obtener_id_empresa, obtener_id_lugar

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

# ==============================================================================
# 1. PANEL PRINCIPAL (GESTIÓN DE RECORRIDOS Y NOTICIAS)
# ==============================================================================
@admin_bp.route('/admin')
@login_required
def admin_panel():
    if current_user.rol != 'admin':
        flash(' Acceso denegado.', 'danger')
        return redirect(url_for('inicio'))

    # --- CAPTURAR FILTROS ---
    f_fecha = request.args.get('fecha', '')
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

    # --- OBTENER LISTAS PARA SELECTS ---
    cur.execute("SELECT nombre FROM lugares ORDER BY nombre ASC")
    lista_lugares = [row[0] for row in cur.fetchall()]
    
    cur.execute("SELECT nombre FROM empresas ORDER BY nombre ASC")
    lista_empresas = [row[0] for row in cur.fetchall()]

    # --- OBTENER NOTICIAS ---
    cur.execute("SELECT id, contenido, fecha_creacion FROM noticias ORDER BY id DESC")
    lista_noticias = cur.fetchall()

    # --- CONSTRUCCIÓN DE SQL DINÁMICO PARA RECORRIDOS ---
    condiciones = ["1=1"]
    params = []
    
    if f_fecha:
        condiciones.append("fecha = %s")
        params.append(f_fecha)
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

    # A. LLEGADAS
    cur.execute(f"SELECT COUNT(*) FROM import_llegadas WHERE {where_clause}", params)
    total_llegadas = cur.fetchone()[0]
    cur.execute(f"""
        SELECT id, hora, empresa_nombre, lugar, anden, fecha 
        FROM import_llegadas 
        WHERE {where_clause} 
        ORDER BY hora ASC LIMIT %s OFFSET %s
    """, (*params, por_pagina, offset))
    llegadas = cur.fetchall()

    # B. SALIDAS
    cur.execute(f"SELECT COUNT(*) FROM import_salidas WHERE {where_clause}", params)
    total_salidas = cur.fetchone()[0]
    cur.execute(f"""
        SELECT id, hora, empresa_nombre, lugar, anden, fecha 
        FROM import_salidas 
        WHERE {where_clause} 
        ORDER BY hora ASC LIMIT %s OFFSET %s
    """, (*params, por_pagina, offset))
    salidas = cur.fetchall()

    cur.close()
    conn.close()

    total_paginas = math.ceil(max(total_llegadas, total_salidas) / por_pagina) if max(total_llegadas, total_salidas) > 0 else 1
    filtros = {'fecha': f_fecha, 'empresa': f_empresa, 'lugar': f_lugar, 'anden': f_anden}

    return render_template('admin.html', 
                           llegadas=llegadas, 
                           salidas=salidas, 
                           lista_noticias=lista_noticias,
                           pagina_actual=pagina, 
                           total_paginas=total_paginas,
                           lista_lugares=lista_lugares,
                           lista_empresas=lista_empresas,
                           filtros=filtros)

# ==============================================================================
# 2. GESTIÓN DE NOTICIAS (NUEVO)
# ==============================================================================

@admin_bp.route('/admin/noticias/nueva', methods=['POST'])
@login_required
def nueva_noticia():
    if current_user.rol != 'admin': return redirect(url_for('inicio'))
    
    contenido = request.form.get('contenido', '').strip()
    if contenido:
        conn = obtener_conexion_admin()
        cur = conn.cursor()
        cur.execute("INSERT INTO noticias (contenido) VALUES (%s)", (contenido,))
        conn.commit()
        cur.close()
        conn.close()
        flash('✅ Noticia publicada correctamente.', 'success')
    else:
        flash('⚠️ El contenido de la noticia no puede estar vacío.', 'warning')
    return redirect(url_for('admin_bp.admin_panel'))

@admin_bp.route('/admin/noticias/eliminar/<int:id>')
@login_required
def eliminar_noticia(id):
    if current_user.rol != 'admin': return redirect(url_for('inicio'))
    
    conn = obtener_conexion_admin()
    cur = conn.cursor()
    cur.execute("DELETE FROM noticias WHERE id = %s", (id,))
    conn.commit()
    cur.close()
    conn.close()
    flash('🗑️ Noticia eliminada.', 'info')
    return redirect(url_for('admin_bp.admin_panel'))

# ==============================================================================
# 3. CREAR / EDITAR RECORRIDO
# ==============================================================================
@admin_bp.route('/admin/editar', methods=['POST'])
@login_required
def editar_registro():
    if current_user.rol != 'admin': return redirect(url_for('inicio'))

    id_reg = request.form.get('id')
    tipo = request.form.get('tipo')
    fecha = request.form.get('fecha')
    hora = request.form.get('hora')
    empresa = request.form.get('empresa')
    lugar = request.form.get('lugar')
    anden = request.form.get('anden')

    tabla = 'import_llegadas' if tipo == 'llegada' else 'import_salidas'
    
    conn = obtener_conexion_admin()
    cur = conn.cursor()

    try:
        # Aseguramos que la empresa y lugar existan en las tablas maestras
        obtener_id_empresa(cur, empresa)
        obtener_id_lugar(cur, lugar)

        if id_reg == '0':  
            cur.execute(f"""
                INSERT INTO {tabla} (lugar, hora, anden, empresa_nombre, fecha)
                VALUES (%s, %s, %s, %s, %s)
            """, (lugar, hora, anden, empresa, fecha))
            flash('✅ Recorrido creado exitosamente.', 'success')
        else:  
            cur.execute(f"""
                UPDATE {tabla} 
                SET fecha=%s, hora=%s, empresa_nombre=%s, lugar=%s, anden=%s
                WHERE id=%s
            """, (fecha, hora, empresa, lugar, anden, id_reg))
            flash('✅ Recorrido actualizado.', 'success')
        
        conn.commit()
    except Exception as e:
        conn.rollback()
        flash(f'❌ Error: {e}', 'danger')
    finally:
        cur.close()
        conn.close()

    return redirect(url_for('admin_bp.admin_panel'))

# ==============================================================================
# 4. ELIMINAR E IMPORTAR
# ==============================================================================
@admin_bp.route('/admin/eliminar/<tipo>/<int:id>')
@login_required
def eliminar(tipo, id):
    if current_user.rol != 'admin': return redirect(url_for('inicio'))
    tabla = "import_llegadas" if tipo == "llegada" else "import_salidas"
    conn = obtener_conexion_admin()
    cur = conn.cursor()
    cur.execute(f"DELETE FROM {tabla} WHERE id = %s", (id,))
    conn.commit()
    cur.close()
    conn.close()
    flash('🗑️ Registro eliminado.', 'info')
    return redirect(url_for('admin_bp.admin_panel'))

@admin_bp.route('/admin/importar', methods=['POST'])
@login_required
def importar_excel():
    if current_user.rol != 'admin': return redirect(url_for('inicio'))
    archivos = request.files.getlist('file')
    carpeta_temp = os.path.join(os.getcwd(), 'temp_uploads')
    if not os.path.exists(carpeta_temp): os.makedirs(carpeta_temp)
    try:
        archivos_guardados = False
        for archivo in archivos:
            if archivo.filename and archivo.filename.endswith('.xlsx'):
                filename = secure_filename(archivo.filename)
                archivo.save(os.path.join(carpeta_temp, filename))
                archivos_guardados = True
        
        if archivos_guardados:
            exito_csv, msg_csv = ejecutar_procesamiento_excel(carpeta_temp)
            if exito_csv:
                exito_db, msg_db = ejecutar_insercion_datos(carpeta_temp)
                flash(f'🚀 {msg_db}', 'success') if exito_db else flash(f'❌ Error DB: {msg_db}', 'danger')
            else:
                flash(f'❌ Error CSV: {msg_csv}', 'danger')
        else:
            flash('⚠️ Seleccione archivos .xlsx válidos.', 'warning')
    except Exception as e:
        flash(f'❌ Error Crítico: {str(e)}', 'danger')
    finally:
        if os.path.exists(carpeta_temp): shutil.rmtree(carpeta_temp)
    return redirect(url_for('admin_bp.admin_panel'))