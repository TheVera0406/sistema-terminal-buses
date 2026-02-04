import pandas as pd
import os
import re
import unicodedata

# 1. CONFIGURACIONES
MESES_MAP = {
    "ENERO": 1, "FEBRERO": 2, "MARZO": 3, "ABRIL": 4, "MAYO": 5, "JUNIO": 6,
    "JULIO": 7, "AGOSTO": 8, "SEPTIEMBRE": 9, "OCTUBRE": 10, "NOVIEMBRE": 11, "DICIEMBRE": 12
}

MAPPING_EMPRESAS = {
    "BELA‰N": "BELEN", "BELAEN": "BELEN", "BELÃ‰N": "BELEN", "BELN": "BELEN", "BELA": "BELEN",
    "AVES AUTRALES": "AVES AUSTRALES", "BUES LINO": "BUSES LINO", "LINO": "BUSES LINO",
    "BLANCA  JARA": "BLANCA JARA", "FIGUEROA": "DARIO FIGUEROA",
    "TRANSPORTE CEA": "BUSES CEA", "TRANSPORTES CEA": "BUSES CEA",
    "TRANSPORTE LOYOLA": "TURISMO LOYOLA", "TURISMO PABLO LOYOLA": "TURISMO LOYOLA",
    "REBECA RECABAL": "RECABAL", "ARANEDA": "ARANDA"
}

def limpiar_texto(texto):
    """
    Limpia el texto convirtiendo a mayúsculas y quitando espacios,
    PERO MANTENIENDO la Ñ y los ACENTOS.
    """
    if pd.isna(texto) or str(texto).strip() == '': return ""
    
    # 1. Convertir a string, mayúsculas y quitar espacios de los extremos
    t = str(texto).upper().strip()
    
    # 2. Normalización 'NFC' (Forma Compuesta)
    # Esto arregla problemas de codificación (ej: letras separadas) 

    try:
        t = unicodedata.normalize('NFC', t)
    except:
        pass

    # 3. Aplicar correcciones manuales (Diccionario de empresas mal escritas)
    return MAPPING_EMPRESAS.get(t, t)

def extraer_dia_de_hoja(nombre_hoja):
    match = re.search(r'(\d{1,2})', str(nombre_hoja))
    if match: return int(match.group(1))
    return None

def buscar_mes_y_anio_en_filas(df_head):
    mes_encontrado = None       
    anio_encontrado = None      
    filas_a_revisar = [str(col) for col in df_head.columns] 
    for i, row in df_head.head(5).iterrows():
        filas_a_revisar.append(" ".join(row.astype(str)))
    for linea in filas_a_revisar:
        linea = linea.upper()
        if mes_encontrado is None:
            for nombre_mes, numero in MESES_MAP.items():
                if nombre_mes in linea:
                    mes_encontrado = numero
                    break 
        if anio_encontrado is None:
            match_anio = re.search(r'(20\d{2})', linea)
            if match_anio:
                anio_encontrado = int(match_anio.group(1))
    return mes_encontrado, anio_encontrado

def encontrar_encabezado(df):
    for i, row in df.head(20).iterrows():
        fila = " ".join(row.astype(str)).upper()
        if "OPERADOR" in fila and ("HORA" in fila or "LLEGADA" in fila or "SALIDA" in fila or "DESTINO" in fila):
            return i + 1
    return 0

def procesar_excel(tipo, carpeta_uploads):
    archivos = [f for f in os.listdir(carpeta_uploads) if f.endswith('.xlsx') and "~$" not in f]
    
    dfs = []
    reporte_errores = [] 
    archivos_procesados = 0

    for archivo in archivos:
        if tipo not in archivo.upper():
            continue 

        ruta_completa = os.path.join(carpeta_uploads, archivo)
        archivos_procesados += 1

        try:
            xls = pd.read_excel(ruta_completa, sheet_name=None)
        except Exception as e:
            reporte_errores.append(f"Error al leer '{archivo}': Formato inválido.")
            continue

        for nombre_hoja, df_raw in xls.items():
            dia = extraer_dia_de_hoja(nombre_hoja)
            mes, anio = buscar_mes_y_anio_en_filas(df_raw)
            
            if dia is None: continue 
            
            if mes is None or anio is None:
                reporte_errores.append(f"Advertencia: Archivo '{archivo}' Hoja '{nombre_hoja}': No se detectó MES o AÑO.")
                continue
            
            skip = encontrar_encabezado(df_raw)
            df = df_raw.iloc[skip:].copy()
            if skip > 0: df.columns = df_raw.iloc[skip-1]
            df.columns = [str(c).strip().upper() for c in df.columns]
            
            cols_map = {}
            posibles_hora = ['HORA SALIDA', 'SALIDA', 'HORA', 'HORARIO', 'HORA LLEGADA', 'HORA LLEGADA.', 'LLEGADA']
            for c in posibles_hora:
                if c in df.columns:
                    cols_map[c] = 'hora'
                    break
            
            if 'DESDE' in df.columns: cols_map['DESDE'] = 'lugar'
            elif 'DESTINO' in df.columns: cols_map['DESTINO'] = 'lugar'
            elif 'ORIGEN' in df.columns: cols_map['ORIGEN'] = 'lugar'
            
            if 'ANDEN' in df.columns: cols_map['ANDEN'] = 'anden'
            
            if 'OPERADOR' in df.columns: cols_map['OPERADOR'] = 'empresa'
            elif 'EMPRESA' in df.columns: cols_map['EMPRESA'] = 'empresa'

            if 'hora' not in cols_map.values():
                continue 

            cols_existentes = {k: v for k, v in cols_map.items() if k in df.columns}
            df = df[list(cols_existentes.keys())].rename(columns=cols_existentes)
            df['fecha'] = f"{anio}-{mes:02d}-{dia:02d}"
            dfs.append(df)

    if not dfs:
        return pd.DataFrame(), reporte_errores

    return pd.concat(dfs, ignore_index=True), reporte_errores

def guardar_csv(df, ruta_salida):
    if df.empty: return False
    
    # Limpiamos texto manteniendo acentos y Ñ
    if 'lugar' in df.columns: df['lugar'] = df['lugar'].apply(limpiar_texto)
    if 'empresa' in df.columns: df['empresa'] = df['empresa'].apply(limpiar_texto)
    
    if 'anden' in df.columns: df['anden'] = pd.to_numeric(df['anden'], errors='coerce').fillna(0).astype(int)
    if 'empresa' in df.columns:
        df = df.dropna(subset=['empresa'])
        df = df[df['empresa'] != ""]
    
    cols = ['lugar', 'hora', 'anden', 'empresa', 'fecha']
    for c in cols: 
        if c not in df.columns: df[c] = ""
    
    # Guardamos en UTF-8 para que la Ñ y los acentos se vean bien en el CSV
    df[cols].to_csv(ruta_salida, index=False, sep=';', encoding='utf-8')
    return True

def ejecutar_procesamiento_excel(carpeta_uploads):
    df_llegadas, errores_llegadas = procesar_excel('LLEGADAS', carpeta_uploads)
    df_salidas, errores_salidas = procesar_excel('SALIDAS', carpeta_uploads)

    ruta_llegadas = os.path.join(carpeta_uploads, 'llegadas_limpio.csv')
    ruta_salidas = os.path.join(carpeta_uploads, 'salidas_limpio.csv')

    mensajes = errores_llegadas + errores_salidas
    exito_total = False

    if not df_llegadas.empty:
        guardar_csv(df_llegadas, ruta_llegadas)
        exito_total = True
    
    if not df_salidas.empty:
        guardar_csv(df_salidas, ruta_salidas)
        exito_total = True

    return exito_total, mensajes