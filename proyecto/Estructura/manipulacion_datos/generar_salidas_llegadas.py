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
    if pd.isna(texto) or str(texto).strip() == '': return ""
    t = str(texto).upper().strip()
    t = t.replace('Ñ', 'N')
    try: 
        t = ''.join(c for c in unicodedata.normalize('NFD', t) if unicodedata.category(c) != 'Mn')
    except: pass
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
    # Buscamos en la carpeta específica de uploads
    archivos = [f for f in os.listdir(carpeta_uploads) if f.endswith('.xlsx') and tipo in f.upper() and "~$" not in f]
    
    if not archivos: return pd.DataFrame(), True

    dfs = []
    for archivo in archivos:
        ruta_completa = os.path.join(carpeta_uploads, archivo)
        try:
            xls = pd.read_excel(ruta_completa, sheet_name=None)
        except Exception as e:
            return pd.DataFrame(), False

        for nombre_hoja, df_raw in xls.items():
            dia = extraer_dia_de_hoja(nombre_hoja)
            mes, anio = buscar_mes_y_anio_en_filas(df_raw)
            if dia is None or mes is None or anio is None: return pd.DataFrame(), False
            
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

            cols_existentes = {k: v for k, v in cols_map.items() if k in df.columns}
            df = df[list(cols_existentes.keys())].rename(columns=cols_existentes)
            df['fecha'] = f"{anio}-{mes:02d}-{dia:02d}"
            dfs.append(df)

    if dfs: return pd.concat(dfs, ignore_index=True), True
    return pd.DataFrame(), True

def guardar_csv(df, ruta_salida):
    if df.empty: return False
    if 'lugar' in df.columns: df['lugar'] = df['lugar'].apply(limpiar_texto)
    if 'empresa' in df.columns: df['empresa'] = df['empresa'].apply(limpiar_texto)
    if 'anden' in df.columns: df['anden'] = pd.to_numeric(df['anden'], errors='coerce').fillna(0).astype(int)
    if 'empresa' in df.columns:
        df = df.dropna(subset=['empresa'])
        df = df[df['empresa'] != ""]
    
    cols = ['lugar', 'hora', 'anden', 'empresa', 'fecha']
    for c in cols: 
        if c not in df.columns: df[c] = ""
    
    df[cols].to_csv(ruta_salida, index=False, sep=';', encoding='utf-8')
    return True

# --- FUNCIÓN PRINCIPAL LLAMADA DESDE FLASK ---
def ejecutar_procesamiento_excel(carpeta_uploads):
    df_llegadas, ok_llegadas = procesar_excel('LLEGADAS', carpeta_uploads)
    df_salidas, ok_salidas = procesar_excel('SALIDAS', carpeta_uploads)

    ruta_llegadas = os.path.join(carpeta_uploads, 'llegadas_limpio.csv')
    ruta_salidas = os.path.join(carpeta_uploads, 'salidas_limpio.csv')

    if ok_llegadas and ok_salidas:
        guardar_csv(df_llegadas, ruta_llegadas)
        guardar_csv(df_salidas, ruta_salidas)
        return True, "CSVs generados correctamente."
    else:
        return False, "Error procesando los Excel. Verifique el formato."
    
# if __name__ == "__main__":
    # Define la carpeta donde están tus archivos Excel
    mi_carpeta = "uploads" 
    
    # Crea la carpeta si no existe
    if not os.path.exists(mi_carpeta):
        os.makedirs(mi_carpeta)
        print(f"Por favor, coloca los archivos Excel en la carpeta: {mi_carpeta}")
    else:
        # Ejecuta el procesamiento
        exito, mensaje = ejecutar_procesamiento_excel(mi_carpeta)
        print(mensaje)