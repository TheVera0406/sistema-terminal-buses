from datetime import datetime
import pytz

def obtener_hora_actual():
    zona_chile = pytz.timezone('America/Santiago')
    return datetime.now(zona_chile)

# Retorna la fecha y hora actual de Chile (Santiago), maneja automáticamente horario de invierno y verano.

