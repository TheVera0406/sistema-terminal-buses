from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import current_user 
import psycopg2
from datetime import datetime
import math
import os
from dotenv import load_dotenv

load_dotenv()

usuario_bp = Blueprint('usuario_bp', __name__)

def obtener_conexion_usuario():
    try:
        return psycopg2.connect(
            host=os.getenv("DB_HOST"),
            database=os.getenv("DB_NAME"),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASS"),
            port=os.getenv("DB_PORT", "5432")
        )
    except Exception as e:
        print(f" Error DB Usuario: {e}")
        return None


#CONSULTA DE RECORRIDOS (PÚBLICA)

@usuario_bp.route('/')
def dashboard():
    conn = obtener_conexion_usuario()
    if not conn:
        flash("Error de conexión a la base de datos.", "danger")
        return redirect(url_for('login'))
    
    cur = conn.cursor()
    
    # --- 1. OBTENER LISTAS MAESTRAS PARA LOS SELECTS ---
    cur.execute("SELECT nombre FROM lugares ORDER BY nombre ASC")
    lista_lugares = [row[0] for row in cur.fetchall()]
    
    cur.execute("SELECT nombre FROM empresas ORDER BY nombre ASC")
    lista_empresas = [row[0] for row in cur.fetchall()]

    # --- 2. CAPTURAR FILTROS DESDE LA URL ---
    f_fecha = request.args.get('fecha', '').strip()
    f_hora = request.args.get('hora', '').strip()
    f_empresa = request.args.get('empresa', '').strip()
    f_lugar = request.args.get('lugar', '').strip()
    f_anden = request.args.get('anden', '').strip()
    
    # Paginación
    pagina = request.args.get('page', 1, type=int)
    por_pagina = 15 
    offset = (pagina - 1) * por_pagina

    # Lógica de fecha por defecto
    if not f_fecha:
        f_fecha = datetime.now().strftime('%Y-%m-%d')
        titulo_estado = f"Programación para Hoy ({f_fecha})"
    else:
        titulo_estado = f"Resultados para el día {f_fecha}"

    # --- 3. CONSTRUIR SQL ---
    condiciones = ["1=1"]
    params = []

    if f_fecha:
        condiciones.append("fecha = %s")
        params.append(f_fecha)
    
    if f_hora:
        condiciones.append("hora::text LIKE %s")
        params.append(f"{f_hora}%")
        
    if f_empresa:
        condiciones.append("empresa_nombre = %s")
        params.append(f_empresa)
        
    if f_lugar:
        condiciones.append("lugar = %s")
        params.append(f_lugar)
        
    if f_anden and f_anden.isdigit():
        condiciones.append("anden = %s")
        params.append(int(f_anden))

    where_clause = "WHERE " + " AND ".join(condiciones)
    order_clause = "ORDER BY hora ASC"

    # --- 4. CONSULTAS DE DATOS (AHORA INCLUYEN 'estado') ---
    
    # A. LLEGADAS
    cur.execute(f"SELECT COUNT(*) FROM import_llegadas {where_clause}", params)
    total_llegadas = cur.fetchone()[0]
    paginas_llegadas = math.ceil(total_llegadas / por_pagina)
    
    # 'estado' al SELECT
    sql_llegadas = f"""
        SELECT id, hora, empresa_nombre, lugar, anden, fecha, estado 
        FROM import_llegadas 
        {where_clause} {order_clause} 
        LIMIT %s OFFSET %s
    """
    cur.execute(sql_llegadas, params + [por_pagina, offset])
    llegadas = cur.fetchall()

    # B. SALIDAS
    cur.execute(f"SELECT COUNT(*) FROM import_salidas {where_clause}", params)
    total_salidas = cur.fetchone()[0]
    paginas_salidas = math.ceil(total_salidas / por_pagina)

    # 'estado' al SELECT
    sql_salidas = f"""
        SELECT id, hora, empresa_nombre, lugar, anden, fecha, estado 
        FROM import_salidas 
        {where_clause} {order_clause} 
        LIMIT %s OFFSET %s
    """
    cur.execute(sql_salidas, params + [por_pagina, offset])
    salidas = cur.fetchall()
    
    cur.close()
    conn.close()

    total_paginas = max(paginas_llegadas, paginas_salidas)
    
    filtros_actuales = {
        'fecha': f_fecha, 
        'hora': f_hora, 
        'empresa': f_empresa, 
        'lugar': f_lugar, 
        'anden': f_anden
    }

    return render_template('usuario.html', 
                           usuario=current_user,
                           llegadas=llegadas, 
                           salidas=salidas, 
                           titulo_estado=titulo_estado,
                           pagina_actual=pagina,
                           total_paginas=total_paginas,
                           lista_lugares=lista_lugares,   
                           lista_empresas=lista_empresas, 
                           filtros=filtros_actuales,
                           total_salidas=total_salidas,
                           total_llegadas=total_llegadas)