"""
Definiciones de prototipos y controladores.

Cada controlador declara sus parámetros de forma que el frontend construya el
formulario dinámicamente. Todos los parámetros se inicializan en 0 en la UI.

Controladores del proyecto: PID, Lógica Difusa, LQR y Modos Deslizantes (SMC).
"""

# --- Prototipos (planta a controlar) ---------------------------------------
# Cada prototipo define un modelo de planta de 2do orden aproximado:
#   K   -> ganancia
#   wn  -> frecuencia natural
#   z   -> amortiguamiento
# El "balancín" (Ball and Beam) es poco amortiguado; el "carrito" (seguidor de
# línea) es más amortiguado. Estos valores solo los usa el SIMULADOR; con el
# ESP32 real la planta es física y estos números se ignoran.
PROTOTIPOS = {
    "balancin": {
        "id": "balancin",
        "nombre": "Balancín (Ball and Beam)",
        "descripcion": "Viga basculante con esfera. Sistema poco amortiguado, propenso a oscilar.",
        "unidad": "cm",
        "planta": {"K": 1.0, "wn": 2.2, "z": 0.18},
    },
    "carrito": {
        "id": "carrito",
        "nombre": "Carrito (seguidor de línea)",
        "descripcion": "Posición respecto al centro de la línea. Respuesta más amortiguada.",
        "unidad": "cm",
        "planta": {"K": 1.0, "wn": 1.6, "z": 0.55},
    },
}

# --- Controladores ----------------------------------------------------------
# Cada 'param' tiene:
#   key      -> identificador interno
#   label    -> etiqueta visible
#   unidad   -> texto de unidad (puede ir vacío)
#   min/max  -> límites de validación (opcionales)
CONTROLADORES = {
    "pid": {
        "id": "pid",
        "nombre": "PID",
        "descripcion": "Proporcional-Integral-Derivativo clásico (mismos parámetros que BallAndBeam_PID.ino).",
        "params": [
            {"key": "setpoint", "label": "Setpoint", "unidad": "cm", "min": 12, "max": 60, "default": 31.0},
            {"key": "kp", "label": "Kp", "unidad": "", "min": 0, "max": 100, "default": 3.0},
            {"key": "ki", "label": "Ki", "unidad": "", "min": 0, "max": 100, "default": 0.2},
            {"key": "kd", "label": "Kd", "unidad": "", "min": 0, "max": 100, "default": 4.0},
        ],
    },
    "difusa": {
        "id": "difusa",
        "nombre": "Lógica Difusa",
        "descripcion": "Difuso Mamdani 7 niveles / 49 reglas (mismos parámetros que BallAndBeam_Difusa.ino).",
        "params": [
            {"key": "setpoint", "label": "Setpoint", "unidad": "cm", "min": 12, "max": 60, "default": 33.5},
            {"key": "e1", "label": "NL", "unidad": "cm", "min": -100, "max": 100, "default": -21.0,
             "grupo": "e_picos", "grupo_label": "E_PICOS", "grupo_unidad": "cm"},
            {"key": "e2", "label": "NM", "unidad": "cm", "min": -100, "max": 100, "default": -14.0,
             "grupo": "e_picos"},
            {"key": "e3", "label": "NS", "unidad": "cm", "min": -100, "max": 100, "default": -7.0,
             "grupo": "e_picos"},
            {"key": "e4", "label": "Z", "unidad": "cm", "min": -100, "max": 100, "default": 0.0,
             "grupo": "e_picos"},
            {"key": "e5", "label": "PS", "unidad": "cm", "min": -100, "max": 100, "default": 7.0,
             "grupo": "e_picos"},
            {"key": "e6", "label": "PM", "unidad": "cm", "min": -100, "max": 100, "default": 14.0,
             "grupo": "e_picos"},
            {"key": "e7", "label": "PL", "unidad": "cm", "min": -100, "max": 100, "default": 21.0,
             "grupo": "e_picos"},
            {"key": "de1", "label": "NL", "unidad": "cm/s", "min": -200, "max": 200, "default": -42.0,
             "grupo": "de_picos", "grupo_label": "DE_PICOS", "grupo_unidad": "cm/s"},
            {"key": "de2", "label": "NM", "unidad": "cm/s", "min": -200, "max": 200, "default": -28.0,
             "grupo": "de_picos"},
            {"key": "de3", "label": "NS", "unidad": "cm/s", "min": -200, "max": 200, "default": -14.0,
             "grupo": "de_picos"},
            {"key": "de4", "label": "Z", "unidad": "cm/s", "min": -200, "max": 200, "default": 0.0,
             "grupo": "de_picos"},
            {"key": "de5", "label": "PS", "unidad": "cm/s", "min": -200, "max": 200, "default": 14.0,
             "grupo": "de_picos"},
            {"key": "de6", "label": "PM", "unidad": "cm/s", "min": -200, "max": 200, "default": 28.0,
             "grupo": "de_picos"},
            {"key": "de7", "label": "PL", "unidad": "cm/s", "min": -200, "max": 200, "default": 42.0,
             "grupo": "de_picos"},
            {"key": "s1", "label": "NL", "unidad": "°", "min": -100, "max": 100, "default": -55.0,
             "grupo": "salida_picos", "grupo_label": "SALIDA_PICOS", "grupo_unidad": "°"},
            {"key": "s2", "label": "NM", "unidad": "°", "min": -100, "max": 100, "default": -36.67,
             "grupo": "salida_picos"},
            {"key": "s3", "label": "NS", "unidad": "°", "min": -100, "max": 100, "default": -18.33,
             "grupo": "salida_picos"},
            {"key": "s4", "label": "Z", "unidad": "°", "min": -100, "max": 100, "default": 0.0,
             "grupo": "salida_picos"},
            {"key": "s5", "label": "PS", "unidad": "°", "min": -100, "max": 100, "default": 18.33,
             "grupo": "salida_picos"},
            {"key": "s6", "label": "PM", "unidad": "°", "min": -100, "max": 100, "default": 36.67,
             "grupo": "salida_picos"},
            {"key": "s7", "label": "PL", "unidad": "°", "min": -100, "max": 100, "default": 55.0,
             "grupo": "salida_picos"},
        ],
    },
    "lqr": {
        "id": "lqr",
        "nombre": "LQR",
        "descripcion": "Realimentación de estado con K1/K2 (mismos parámetros que BallAndBeam_LQR.ino; K1/K2 se calculan aparte en LQR_Ball_Beam.m).",
        "params": [
            {"key": "setpoint", "label": "Setpoint", "unidad": "cm", "min": 12, "max": 60, "default": 33.5},
            {"key": "k1", "label": "K1 (posición)", "unidad": "", "min": 0, "max": 100, "default": 2.0279},
            {"key": "k2", "label": "K2 (velocidad)", "unidad": "", "min": 0, "max": 100, "default": 1.3293},
        ],
    },
    "smc": {
        "id": "smc",
        "nombre": "Modos Deslizantes (SMC)",
        "descripcion": "Superficie s = x2 + λ·x1 con capa límite φ (mismos parámetros que BallAndBeam_SMC.ino).",
        "params": [
            {"key": "setpoint", "label": "Setpoint", "unidad": "cm", "min": 12, "max": 60, "default": 31.0},
            {"key": "lambda", "label": "λ (LAMBDA)", "unidad": "", "min": 0, "max": 50, "default": 10.0},
            {"key": "eta", "label": "η (K_SMC)", "unidad": "", "min": 0, "max": 200, "default": 5.5},
            {"key": "phi", "label": "φ (PHI)", "unidad": "", "min": 0.001, "max": 100, "default": 2.5},
        ],
    },
}


# --- Controladores del CARRITO seguidor de línea ----------------------------
# Mismos parámetros y valores por defecto que los sketches MEJORADOS ya
# probados en la pista (CarritoLinea_X_Mejorado.ino). Las "key" son los
# nombres que espera firmware/CarritoLinea_Web (GET /iniciar?ctrl=..&kp=..).
# "base" = velocidad de crucero (PWM 0-255), igual que VELOCIDAD_BASE.
_BASE = {"key": "base", "label": "Velocidad base", "unidad": "PWM", "min": 0, "max": 255, "default": 180}


def _grupo(prefijo, picos, unidad, etiqueta, lim):
    nombres = ["NL", "NM", "NS", "Z", "PS", "PM", "PL"]
    out = []
    for i, (n, v) in enumerate(zip(nombres, picos)):
        d = {"key": f"{prefijo}{i + 1}", "label": n, "unidad": unidad,
             "min": -lim, "max": lim, "default": v, "grupo": f"{prefijo}_picos_carrito"}
        if i == 0:
            d["grupo_label"] = etiqueta
            d["grupo_unidad"] = unidad
        out.append(d)
    return out


CONTROLADORES_CARRITO = {
    "pid": {
        "id": "pid",
        "nombre": "PID",
        "descripcion": "Proporcional-Integral-Derivativo con anti-windup (mismos parámetros que CarritoLinea_PID_Mejorado.ino).",
        "params": [
            dict(_BASE),
            {"key": "kp", "label": "Kp", "unidad": "", "min": 0, "max": 500, "default": 100.0},
            {"key": "ki", "label": "Ki", "unidad": "", "min": 0, "max": 500, "default": 0.0},
            {"key": "kd", "label": "Kd", "unidad": "", "min": 0, "max": 100, "default": 0.5},
        ],
    },
    "difusa": {
        "id": "difusa",
        "nombre": "Lógica Difusa",
        "descripcion": "Difuso Mamdani 7 niveles / 49 reglas (mismos parámetros que CarritoLinea_Difusa_Mejorado.ino).",
        "params": [dict(_BASE)]
        + _grupo("e", [-2.0, -1.0, -0.5, 0.0, 0.5, 1.0, 2.0], "pos", "E_PICOS", 5)
        + _grupo("de", [-45.0, -30.0, -15.0, 0.0, 15.0, 30.0, 45.0], "pos/s", "DE_PICOS", 200)
        + _grupo("s", [-220.0, -140.0, -80.0, 0.0, 80.0, 140.0, 220.0], "PWM", "SALIDA_PICOS", 510),
    },
    "lqr": {
        "id": "lqr",
        "nombre": "LQR",
        "descripcion": "Realimentación de estado con observador (mismos parámetros que CarritoLinea_LQR_Mejorado.ino; K1/K2 se calculan en CarritoLinea_LQR.m).",
        "params": [
            dict(_BASE),
            {"key": "k1", "label": "K1 (desplazamiento)", "unidad": "PWM/cm", "min": 0, "max": 500, "default": 45.4545},
            {"key": "k2", "label": "K2 (ángulo)", "unidad": "PWM/rad", "min": 0, "max": 1000, "default": 194.9067},
        ],
    },
    "smc": {
        "id": "smc",
        "nombre": "Modos Deslizantes (SMC)",
        "descripcion": "Superficie s = λ·x1 + v·x2 con capa límite φ (mismos parámetros que CarritoLinea_SMC_Mejorado.ino).",
        "params": [
            dict(_BASE),
            {"key": "lambda", "label": "λ (LAMBDA)", "unidad": "", "min": 0, "max": 50, "default": 3.0},
            {"key": "ksmc", "label": "K_SMC", "unidad": "", "min": 0, "max": 500, "default": 32.0},
            {"key": "phi", "label": "φ (PHI)", "unidad": "", "min": 0.001, "max": 100, "default": 6.6},
        ],
    },
}

# Qué controladores usa cada prototipo
CONTROLADORES_POR_PROTOTIPO = {
    "balancin": CONTROLADORES,
    "carrito": CONTROLADORES_CARRITO,
}


def _lista(dic):
    return [
        {"id": c["id"], "nombre": c["nombre"], "descripcion": c["descripcion"], "params": c["params"]}
        for c in dic.values()
    ]


def meta():
    """Estructura que consume el frontend para armar Selección y formularios."""
    return {
        "prototipos": [
            {k: v[k] for k in ("id", "nombre", "descripcion", "unidad")}
            for v in PROTOTIPOS.values()
        ],
        # lista general (balancín), se mantiene por compatibilidad
        "controladores": _lista(CONTROLADORES),
        # lista propia de cada prototipo
        "controladores_por_prototipo": {
            pid: _lista(dic) for pid, dic in CONTROLADORES_POR_PROTOTIPO.items()
        },
    }
