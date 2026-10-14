"""
Fuente de telemetría.

Implementaciones intercambiables:
  - SimulatorSource: simula la planta + el controlador (sin hardware).
  - Esp32SerialSource: lee líneas por USB del ESP32 (protocolo serial abajo).
  - Esp32WifiSource: igual que la serial pero por WiFi (TCP).
  - Esp32HttpSource: carrito seguidor de línea, peticiones HTTP cortas a la
    red WiFi propia del ESP32 (firmware/CarritoLinea_Web).

Ambas producen dicts de telemetría:  {t, ref, vc, error, u}
y detectan cuándo se alcanzó el setpoint (done).

Protocolo serial ESP32 (para cuando conectes el hardware):
  PC  -> ESP32 :  START,<controlador>,<p1>,<p2>,...\n
  PC  -> ESP32 :  STOP\n
  ESP32 -> PC  :  DATA,<t>,<ref>,<vc>,<error>,<u>\n
  ESP32 -> PC  :  DONE\n
"""
import json
import math
import random
import socket
import time
import urllib.error
import urllib.parse
import urllib.request

DT = 0.03            # paso de integración / muestreo (s)  ~33 Hz
MAX_T = 25.0         # tope de seguridad de duración (s)
U_MIN, U_MAX = -100.0, 100.0
TOL_STEADY_S = 1.0   # tiempo sostenido dentro de tolerancia para dar "done"


class SimulatorSource:
    def __init__(self, prototipo, controlador_id, params, controller):
        self.planta = prototipo["planta"]
        self.controller = controller
        self.setpoint = float(params.get("setpoint", 0.0))
        self.dt = DT
        # estado de la planta 2do orden: [y, y']
        self.y = 0.0
        self.yd = 0.0
        self.t = 0.0
        self._steady_acc = 0.0
        self.T, self.REF, self.VC, self.ERR, self.U = [], [], [], [], []

    def _tolerance(self):
        return max(0.02 * abs(self.setpoint), 0.3)

    def step(self):
        K = self.planta["K"]; wn = self.planta["wn"]; z = self.planta["z"]
        # medición con ruido leve
        y_meas = self.y + random.gauss(0, 0.02)
        u = self.controller.step(y_meas, self.dt)
        u = max(U_MIN, min(U_MAX, u))
        # dinámica de la planta (2do orden, Euler)
        ydd = K * wn * wn * u - 2 * z * wn * self.yd - wn * wn * self.y
        self.yd += ydd * self.dt
        self.y += self.yd * self.dt
        self.t += self.dt

        ref = self.setpoint
        vc = self.y
        err = ref - vc

        self.T.append(round(self.t, 3)); self.REF.append(round(ref, 4))
        self.VC.append(round(vc, 4)); self.ERR.append(round(err, 4))
        self.U.append(round(u, 4))

        # ¿setpoint alcanzado de forma sostenida?
        if abs(err) <= self._tolerance():
            self._steady_acc += self.dt
        else:
            self._steady_acc = 0.0
        done = self._steady_acc >= TOL_STEADY_S or self.t >= MAX_T
        reason = None
        if done:
            reason = "setpoint" if self._steady_acc >= TOL_STEADY_S else "timeout"

        return {
            "t": round(self.t, 3),
            "ref": round(ref, 4),
            "vc": round(vc, 4),
            "error": round(err, 4),
            "u": round(u, 4),
            "done": done,
            "reason": reason,
        }

    def arrays(self):
        return self.T, self.REF, self.VC, self.ERR


SIN_DATOS_S = 2.0    # si el ESP32 pasa este tiempo sin mandar nada, se da por perdida la conexión


def _parse_linea(linea, T, REF, VC, ERR):
    """Convierte una línea del ESP32 en un dict de telemetría (o None)."""
    if linea == "DONE":
        return {"t": T[-1] if T else 0, "done": True, "reason": "setpoint"}
    if linea.startswith("DATA,"):
        partes = linea.split(",")
        if len(partes) != 6:
            return None   # línea incompleta o dañada: se ignora
        try:
            t, ref, vc, err, u = map(float, partes[1:])
        except ValueError:
            return None
        T.append(t); REF.append(ref); VC.append(vc); ERR.append(err)
        return {"t": t, "ref": ref, "vc": vc, "error": err, "u": u,
                "done": False, "reason": None}
    return None   # mensajes de depuración u otros: se ignoran


class Esp32WifiSource:
    """
    Lectura real del ESP32 por WiFi (TCP). Se activa poniendo
    USE_SIMULATOR=False y CONEXION="wifi" en main.py.

    - Lee TODAS las líneas que ya llegaron en cada paso (sin retraso acumulado).
    - El socket no bloquea, así el backend sigue atendiendo el botón Finalizar.
    - Si el ESP32 cierra la conexión o deja de mandar datos SIN_DATOS_S
      segundos (p. ej. porque se reinició), lanza un error en vez de
      quedarse esperando para siempre.
    """
    def __init__(self, prototipo, controlador_id, params, host, port=3333, timeout=5.0):
        self.host = host
        try:
            self.sock = socket.create_connection((host, port), timeout=timeout)
        except OSError as e:
            raise ConnectionError(
                f"No se pudo conectar con el ESP32 en {host}:{port}. "
                f"Revisa que la laptop esté conectada a la red WiFi del prototipo "
                f"y que el ESP32 esté encendido. ({e})"
            ) from None
        self.sock.setblocking(False)
        self._buffer = b""
        self.T, self.REF, self.VC, self.ERR = [], [], [], []
        vals = ",".join(str(v) for v in params.values())
        self.sock.setblocking(True)
        self.sock.sendall(f"START,{controlador_id},{vals}\n".encode())
        self.sock.setblocking(False)
        self._ultimo_dato = time.monotonic()

    def step(self):
        # 1) leer todo lo que haya llegado
        while True:
            try:
                chunk = self.sock.recv(4096)
            except (BlockingIOError, InterruptedError):
                break                      # no hay más datos por ahora
            except OSError as e:
                raise ConnectionError(f"Se perdió la conexión con el ESP32 ({e}).") from None
            if not chunk:
                raise ConnectionError(
                    "El ESP32 cerró la conexión (puede que se haya reiniciado)."
                )
            self._buffer += chunk
            self._ultimo_dato = time.monotonic()

        # 2) separar en líneas completas
        salida = []
        while b"\n" in self._buffer:
            linea, self._buffer = self._buffer.split(b"\n", 1)
            tel = _parse_linea(linea.decode(errors="ignore").strip(),
                               self.T, self.REF, self.VC, self.ERR)
            if tel:
                salida.append(tel)
                if tel["done"]:
                    break

        # 3) ¿lleva mucho tiempo sin mandar nada?
        if not salida and time.monotonic() - self._ultimo_dato > SIN_DATOS_S:
            raise TimeoutError(
                f"El ESP32 dejó de mandar datos hace más de {SIN_DATOS_S:.0f} s "
                f"(puede que se haya reiniciado o que se haya caído el WiFi)."
            )
        return salida

    def stop(self):
        try:
            self.sock.setblocking(True)
            self.sock.settimeout(0.5)
            self.sock.sendall(b"STOP\n")
        except Exception:
            pass
        try:
            self.sock.close()
        except Exception:
            pass

    def arrays(self):
        return self.T, self.REF, self.VC, self.ERR


class Esp32SerialSource:
    """
    Lectura real del ESP32 por puerto serial (cable USB). Se activa poniendo
    USE_SIMULATOR=False y CONEXION="serial" en main.py.
    Requiere: pip install pyserial
    """
    def __init__(self, prototipo, controlador_id, params, port, baud=115200):
        import serial  # import diferido para no exigir pyserial en modo simulador
        self.ser = serial.Serial(port, baud, timeout=0)
        # Al abrir el puerto, la mayoría de placas ESP32 se reinician solas
        # (toggle de DTR/RTS). Se espera a que termine de arrancar y se
        # limpia la basura del buffer antes de mandar START.
        time.sleep(2.0)
        self.ser.reset_input_buffer()
        self._buffer = b""
        self.T, self.REF, self.VC, self.ERR = [], [], [], []
        vals = ",".join(str(v) for v in params.values())
        self.ser.write(f"START,{controlador_id},{vals}\n".encode())
        self._ultimo_dato = time.monotonic()

    def step(self):
        try:
            n = self.ser.in_waiting
            if n:
                self._buffer += self.ser.read(n)
                self._ultimo_dato = time.monotonic()
        except Exception as e:
            raise ConnectionError(f"Se perdió la conexión serial con el ESP32 ({e}).") from None

        salida = []
        while b"\n" in self._buffer:
            linea, self._buffer = self._buffer.split(b"\n", 1)
            tel = _parse_linea(linea.decode(errors="ignore").strip(),
                               self.T, self.REF, self.VC, self.ERR)
            if tel:
                salida.append(tel)
                if tel["done"]:
                    break

        if not salida and time.monotonic() - self._ultimo_dato > SIN_DATOS_S:
            raise TimeoutError(
                f"El ESP32 dejó de mandar datos hace más de {SIN_DATOS_S:.0f} s."
            )
        return salida

    def stop(self):
        try:
            self.ser.write(b"STOP\n")
            self.ser.close()
        except Exception:
            pass

    def arrays(self):
        return self.T, self.REF, self.VC, self.ERR


# Motivos de fin que manda firmware/CarritoLinea_Web en "fin"
_FIN_CARRITO = ("manual", "tiempo", "linea", "conexion")


class Esp32HttpSource:
    """
    Carrito seguidor de línea por WiFi con peticiones HTTP cortas (pregunta
    y respuesta), igual que las páginas de prueba de cada controlador.
    Se usa con CONEXION["carrito"] = "http" en main.py.

      GET /iniciar?ctrl=pid&base=180&kp=100&...   arranca la corrida
      GET /datos?desde=N                           muestras nuevas
      GET /detener                                 Finalizar

    Si una petición se pierde, la siguiente recupera las muestras que
    faltaban (el ESP32 las guarda). Solo si pasan SIN_DATOS_S segundos sin
    ninguna respuesta se da por perdida la conexión.
    """
    bloqueante = True        # main.py la llama en un hilo aparte
    INTERVALO_S = 0.1        # cada cuánto se piden datos
    TIMEOUT_S = 0.8          # espera máxima de cada petición

    def __init__(self, prototipo, controlador_id, params, host, red_wifi="ESP32-CARRITO"):
        self.base_url = f"http://{host}"
        # Sin proxy: la IP del ESP32 es local (Windows a veces tiene un
        # proxy del sistema configurado que no sabe llegar a 192.168.5.1).
        self._opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        self.T, self.REF, self.VC, self.ERR = [], [], [], []
        self._desde = 0
        self._fin = None
        self._ultimo_ok = time.monotonic()
        self._ultima_peticion = 0.0

        consulta = {"ctrl": controlador_id}
        for k, v in params.items():
            consulta[k] = f"{float(v):g}"
        try:
            self._get("/iniciar?" + urllib.parse.urlencode(consulta), timeout=3.0)
        except urllib.error.HTTPError as e:
            detalle = e.read().decode(errors="ignore")
            raise ValueError(f"El carrito rechazó la corrida ({e.code}): {detalle}") from None
        except (urllib.error.URLError, OSError) as e:
            raise ConnectionError(
                f"No se pudo conectar con el carrito en {host}. Revisa que la laptop "
                f"esté conectada a la red WiFi \"{red_wifi}\" (contraseña 12345678) "
                f"y que el carrito esté encendido. ({getattr(e, 'reason', e)})"
            ) from None
        self._ultimo_ok = time.monotonic()

    def _get(self, ruta, timeout=None):
        with self._opener.open(self.base_url + ruta, timeout=timeout or self.TIMEOUT_S) as r:
            return r.read().decode(errors="ignore")

    def _pedir_datos(self):
        """Pide /datos y guarda las muestras nuevas. Devuelve (lista, info)."""
        info = json.loads(self._get(f"/datos?desde={self._desde}"))
        salida = []
        for fila in info.get("m", []):
            try:
                t, ref, vc, err, u = (float(x) for x in fila)
            except (TypeError, ValueError):
                continue
            self.T.append(t); self.REF.append(ref); self.VC.append(vc); self.ERR.append(err)
            salida.append({"t": t, "ref": ref, "vc": vc, "error": err, "u": u,
                           "done": False, "reason": None})
        self._desde = int(info.get("desde", self._desde)) + len(info.get("m", []))
        return salida, info

    def step(self):
        if self._fin:
            return [{"t": self.T[-1] if self.T else 0, "done": True, "reason": self._fin}]
        ahora = time.monotonic()
        if ahora - self._ultima_peticion < self.INTERVALO_S:
            return []
        self._ultima_peticion = ahora
        try:
            salida, info = self._pedir_datos()
        except (urllib.error.URLError, OSError, ValueError):
            # Una petición perdida no es grave; la siguiente trae lo que falte.
            if time.monotonic() - self._ultimo_ok > SIN_DATOS_S:
                raise ConnectionError(
                    f"El carrito no responde hace más de {SIN_DATOS_S:.0f} s "
                    f"(se apagó, se reinició o la laptop se salió de su red WiFi)."
                ) from None
            return []
        self._ultimo_ok = time.monotonic()

        total = int(info.get("total", 0))
        fin = info.get("fin") or ""
        if not info.get("corriendo") and not fin:
            # El ESP32 está detenido sin motivo de fin: se reinició.
            raise ConnectionError("El carrito se reinició durante la corrida "
                                  "(revisa la batería y las conexiones).")
        if fin and self._desde >= total:
            self._fin = fin if fin in _FIN_CARRITO else "manual"
            salida.append({"t": self.T[-1] if self.T else 0, "done": True, "reason": self._fin})
        return salida

    def stop(self):
        """Finalizar: detiene el carrito y recoge las últimas muestras."""
        try:
            self._get("/detener")
        except Exception:
            pass
        for _ in range(10):   # como mucho 10 x 100 muestras pendientes
            try:
                salida, info = self._pedir_datos()
            except Exception:
                break
            if self._desde >= int(info.get("total", 0)):
                break

    def arrays(self):
        return self.T, self.REF, self.VC, self.ERR
