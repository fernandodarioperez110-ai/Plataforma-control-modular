"""
Leyes de control usadas por el simulador.

Cada controlador es una clase con .step(y, dt) -> u  (señal de control),
donde y es la variable controlada medida. Con el ESP32 real, estas leyes
viven en el firmware; aquí replican el comportamiento para poder probar todo
sin hardware.

Controladores: PID, Fuzzy (difusa), LQR y SMC (modos deslizantes).
LQR y SMC son basados en modelo: usan el modelo de 2do orden de la planta.
"""

DT = 0.03  # periodo de muestreo (s), coherente con source.py


class PID:
    def __init__(self, setpoint, kp, ki, kd):
        self.sp = setpoint
        self.kp, self.ki, self.kd = kp, ki, kd
        self._int = 0.0
        self._prev_e = None

    def step(self, y, dt):
        e = self.sp - y
        self._int += e * dt
        de = 0.0 if self._prev_e is None else (e - self._prev_e) / dt
        self._prev_e = e
        return self.kp * e + self.ki * self._int + self.kd * de


class Fuzzy:
    """
    Controlador difuso Mamdani de 7 niveles / 49 reglas, igual al usado en
    BallAndBeam_Difusa.ino. Recibe los picos de las funciones de membresía
    triangulares (e_picos, de_picos, salida_picos, 7 valores cada uno) en
    vez de ganancias de escalado.
    """
    N = 7

    def __init__(self, setpoint, e_picos, de_picos, salida_picos):
        self.sp = setpoint
        self.e_picos = e_picos
        self.de_picos = de_picos
        self.salida_picos = salida_picos
        self._prev_e = None

    @classmethod
    def _fuzzificar(cls, x, picos):
        if x <= picos[0]:
            return (0, 1.0), (0, 0.0)
        if x >= picos[cls.N - 1]:
            return (cls.N - 1, 1.0), (cls.N - 1, 0.0)
        for k in range(cls.N - 1):
            if picos[k] <= x <= picos[k + 1]:
                rango = picos[k + 1] - picos[k]
                g_sup = (x - picos[k]) / rango if rango else 0.0
                g_inf = 1.0 - g_sup
                return (k, g_inf), (k + 1, g_sup)
        return (0, 0.0), (0, 0.0)

    def step(self, y, dt):
        e = self.sp - y
        de = 0.0 if self._prev_e is None else (e - self._prev_e) / dt
        self._prev_e = e

        (iE0, gE0), (iE1, gE1) = self._fuzzificar(e, self.e_picos)
        (iDE0, gDE0), (iDE1, gDE1) = self._fuzzificar(de, self.de_picos)

        num = den = 0.0
        for idx_e, g_e in ((iE0, gE0), (iE1, gE1)):
            if g_e <= 0:
                continue
            for idx_de, g_de in ((iDE0, gDE0), (iDE1, gDE1)):
                if g_de <= 0:
                    continue
                disparo = min(g_e, g_de)
                idx_salida = max(0, min(self.N - 1, idx_e + idx_de - 3))
                num += disparo * self.salida_picos[idx_salida]
                den += disparo
        return 0.0 if den == 0 else num / den


class LQR:
    """
    Realimentación de estado con K1/K2 ya calculados (igual que
    BallAndBeam_LQR.ino, donde K1/K2 se obtienen aparte con LQR_Ball_Beam.m
    y no se recalculan en tiempo real):

        u = -(k1*(y - sp) + k2*vel)
    """
    def __init__(self, setpoint, k1, k2, planta=None):
        self.sp = setpoint
        self.k1 = k1
        self.k2 = k2
        self._prev_y = None

    def step(self, y, dt):
        vel = 0.0 if self._prev_y is None else (y - self._prev_y) / dt
        self._prev_y = y
        return -(self.k1 * (y - self.sp) + self.k2 * vel)


class SMC:
    """
    Control por modos deslizantes (igual que BallAndBeam_SMC.ino):

        s = x2 + lambda*x1          (x1 = y - sp, x2 = velocidad)
        u = -(lambda*x2 + k_smc*sat(s/phi))
    """
    def __init__(self, setpoint, lam, k_smc, phi, planta=None):
        self.sp = setpoint
        self.lam = lam
        self.k_smc = k_smc
        self.phi = max(phi, 1e-3)
        self._prev_e = None

    def step(self, y, dt):
        x1 = y - self.sp
        x2 = 0.0 if self._prev_e is None else (x1 - self._prev_e) / dt
        self._prev_e = x1
        s = x2 + self.lam * x1
        sat = max(-1.0, min(1.0, s / self.phi))
        return -(self.lam * x2 + self.k_smc * sat)


def build_controller(controlador_id, params, planta):
    # El carrito no tiene setpoint (siempre es la línea centrada = 0) y su
    # SMC usa "ksmc" en lugar de "eta".
    p = dict(params)
    p.setdefault("setpoint", 0.0)
    if "eta" not in p and "ksmc" in p:
        p["eta"] = p["ksmc"]
    if controlador_id == "pid":
        return PID(p["setpoint"], p["kp"], p["ki"], p["kd"])
    if controlador_id == "difusa":
        e_picos = [p["e1"], p["e2"], p["e3"], p["e4"], p["e5"], p["e6"], p["e7"]]
        de_picos = [p["de1"], p["de2"], p["de3"], p["de4"], p["de5"], p["de6"], p["de7"]]
        s_picos = [p["s1"], p["s2"], p["s3"], p["s4"], p["s5"], p["s6"], p["s7"]]
        return Fuzzy(p["setpoint"], e_picos, de_picos, s_picos)
    if controlador_id == "lqr":
        return LQR(p["setpoint"], p["k1"], p["k2"], planta)
    if controlador_id == "smc":
        return SMC(p["setpoint"], p["lambda"], p["eta"], p["phi"], planta)
    raise ValueError(f"Controlador desconocido: {controlador_id}")
