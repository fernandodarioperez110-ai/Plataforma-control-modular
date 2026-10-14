"""
Cálculo de métricas de desempeño a partir de la telemetría de una corrida.

Entradas: listas de tiempo (t), referencia (ref), variable controlada (vc)
y error (e = ref - vc).
"""
import math


def compute_metrics(t, ref, vc, error):
    n = len(t)
    if n == 0:
        return {
            "tiempo_ejecucion": 0.0,
            "error_rms": 0.0,
            "sobreimpulso": 0.0,
            "error_estacionario": 0.0,
        }

    # Tiempo de ejecución: duración total de la corrida
    tiempo_ejecucion = float(t[-1] - t[0])

    # Error RMS: raíz del promedio de los errores al cuadrado
    error_rms = math.sqrt(sum(e * e for e in error) / n)

    # Setpoint de referencia (última referencia, normalmente constante)
    setpoint = ref[-1] if ref else 0.0

    # Sobreimpulso (%): cuánto se pasó el pico de la VC por encima del setpoint,
    # relativo al salto desde el valor inicial. Solo aplica si hay salto real.
    y0 = vc[0]
    salto = setpoint - y0
    if abs(salto) > 1e-9:
        if salto > 0:
            pico = max(vc)
            sobre = (pico - setpoint) / salto
        else:
            pico = min(vc)
            sobre = (setpoint - pico) / (-salto)
        sobreimpulso = max(0.0, sobre * 100.0)
    else:
        sobreimpulso = 0.0

    # Error estacionario: |error| promedio en el último 15% de la corrida
    cola = max(1, int(n * 0.15))
    error_estacionario = abs(sum(error[-cola:]) / cola)

    return {
        "tiempo_ejecucion": round(tiempo_ejecucion, 3),
        "error_rms": round(error_rms, 4),
        "sobreimpulso": round(sobreimpulso, 2),
        "error_estacionario": round(error_estacionario, 4),
    }
