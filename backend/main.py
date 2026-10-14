"""
Backend FastAPI: puente entre el navegador (WebSocket) y la planta
(simulador o ESP32 por serial), cálculo de métricas y persistencia.

Correr:  uvicorn main:app --reload --port 8000   (desde la carpeta backend)
"""
import asyncio
import json
import traceback

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import os

import controllers as ctrl
import control_laws
import source as src
import metrics as mx
import database as db

# --- Configuración ----------------------------------------------------------
# Cambia a False y ajusta SERIAL_PORT cuando conectes el ESP32 real.
USE_SIMULATOR = False
SERIAL_PORT = "COM7"   # Windows: "COM7"

# Modo de conexión de CADA prototipo con su ESP32 real:
#   "serial" -> cable USB (puerto SERIAL_PORT)
#   "wifi"   -> TCP a la red propia del ESP32
#   "http"   -> peticiones HTTP cortas a la red propia del ESP32
CONEXION = {
    "balancin": "serial",   # firmware/BallAndBeam_Web_Cable
    "carrito":  "http",     # firmware/CarritoLinea_Web
}
# Cada ESP32 crea su propia red WiFi (modo Access Point). Antes de pulsar
# Iniciar, conecta la laptop a la red del prototipo que vas a usar.
#   balancin -> red "ESP32-BALANCIN"   IP 192.168.4.1
#   carrito  -> red "ESP32-CARRITO"    IP 192.168.5.1  (contraseña 12345678)
ESP32_IPS = {
    "balancin": "192.168.4.1",
    "carrito":  "192.168.5.1",
}
ESP32_TCP_PORT = 3333

app = FastAPI(title="Flujo Controlador ESP32")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _startup():
    db.init_db()


@app.get("/api/meta")
def get_meta():
    return ctrl.meta()


@app.get("/api/logs")
def get_logs():
    return db.last_runs(50)


@app.get("/api/logs/{run_id}")
def get_log(run_id: int):
    run = db.get_run(run_id)
    if not run:
        return JSONResponse({"error": "no encontrado"}, status_code=404)
    return run


class DeleteRunsBody(BaseModel):
    ids: list[int]


@app.delete("/api/logs")
def delete_logs(body: DeleteRunsBody):
    deleted = db.delete_runs(body.ids)
    return {"ok": True, "deleted": deleted}


def _build_source(prototipo_id, controlador_id, params):
    prototipo = ctrl.PROTOTIPOS[prototipo_id]
    if controlador_id not in ctrl.CONTROLADORES_POR_PROTOTIPO[prototipo_id]:
        raise ValueError(f"El controlador '{controlador_id}' no existe para {prototipo['nombre']}.")
    if USE_SIMULATOR:
        controller = control_laws.build_controller(controlador_id, params, prototipo["planta"])
        return src.SimulatorSource(prototipo, controlador_id, params, controller)
    modo = CONEXION.get(prototipo_id, "serial")
    if modo == "http":
        return src.Esp32HttpSource(prototipo, controlador_id, params, ESP32_IPS[prototipo_id])
    if modo == "wifi":
        ip = ESP32_IPS[prototipo_id]
        return src.Esp32WifiSource(prototipo, controlador_id, params, ip, ESP32_TCP_PORT)
    return src.Esp32SerialSource(prototipo, controlador_id, params, SERIAL_PORT)


async def _llamar(source, metodo):
    """Las fuentes HTTP esperan respuesta de la red: se llaman en otro hilo
    para que el backend siga atendiendo el botón Finalizar mientras tanto."""
    f = getattr(source, metodo)
    if getattr(source, "bloqueante", False):
        return await asyncio.to_thread(f)
    return f()


@app.websocket("/ws")
async def ws_control(ws: WebSocket):
    await ws.accept()
    stop_flag = {"stop": False}

    async def _listen():
        # escucha mensajes del cliente (p. ej. Finalizar) en paralelo
        try:
            while True:
                msg = await ws.receive_text()
                data = json.loads(msg)
                if data.get("action") == "stop":
                    stop_flag["stop"] = True
                    return
        except WebSocketDisconnect:
            stop_flag["stop"] = True

    try:
        # primer mensaje: configuración de la corrida
        cfg = json.loads(await ws.receive_text())
        prototipo_id = cfg["prototipo"]
        controlador_id = cfg["controlador"]
        params = cfg["params"]

        source = await asyncio.to_thread(_build_source, prototipo_id, controlador_id, params)
        listener = asyncio.create_task(_listen())

        reason = "manual"
        aviso = None
        terminado = False
        while not stop_flag["stop"] and not terminado:
            try:
                # Puede devolver None, un dato (simulador) o una lista con
                # TODAS las líneas que llegaron del ESP32 (así no se acumula
                # retraso en la gráfica).
                tels = await _llamar(source, "step")
            except (ConnectionError, TimeoutError, OSError) as e:
                # Se cortó la conexión o el ESP32 dejó de mandar datos
                # (p. ej. se reinició). Se termina la corrida en vez de
                # quedarse esperando para siempre.
                reason = "conexion"
                aviso = str(e)
                break
            if tels is None:
                tels = []
            elif isinstance(tels, dict):
                tels = [tels]
            for tel in tels:
                if "vc" in tel:   # el aviso DONE no trae datos para graficar
                    await ws.send_text(json.dumps({"type": "telemetry", **tel}))
                if tel.get("done"):
                    reason = tel.get("reason") or "setpoint"
                    terminado = True
                    break
            await asyncio.sleep(src.DT)

        listener.cancel()

        # Al pulsar Finalizar, recoge las últimas líneas que ya habían
        # llegado para no perderlas.
        if reason == "manual":
            try:
                await _llamar(source, "step")
            except Exception:
                pass

        # cierre de la conexión con el ESP32 si aplica
        if hasattr(source, "stop"):
            await _llamar(source, "stop")

        # Si la conexión se cayó antes de recibir cualquier dato, no se
        # guarda una corrida vacía: solo se avisa del error.
        if reason == "conexion" and not source.arrays()[0]:
            await ws.send_text(json.dumps({"type": "error", "message": aviso}))
            return

        # métricas + guardado
        T, REF, VC, ERR = source.arrays()
        metrics = mx.compute_metrics(T, REF, VC, ERR)
        telemetria = {"t": T, "ref": REF, "vc": VC, "error": ERR}
        run_id = db.save_run(prototipo_id, controlador_id, params, metrics, telemetria)

        await ws.send_text(json.dumps({
            "type": "done",
            "reason": reason,
            "aviso": aviso,
            "metrics": metrics,
            "run_id": run_id,
        }))
    except WebSocketDisconnect:
        pass
    except Exception as e:
        # Imprime el error completo en la terminal del backend para poder
        # diagnosticarlo (p. ej. "ConnectionRefusedError" o "timed out" si
        # no logra conectar con el ESP32 por WiFi), y además se lo manda al
        # navegador para que no se quede la pantalla sin explicación.
        print("ERROR en /ws:")
        traceback.print_exc()
        try:
            await ws.send_text(json.dumps({"type": "error", "message": f"{type(e).__name__}: {e}"}))
        except Exception:
            pass
    finally:
        try:
            await ws.close()
        except Exception:
            pass


# --- Servir el build de React (producción) ----------------------------------
DIST = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")
if os.path.isdir(DIST):
    app.mount("/assets", StaticFiles(directory=os.path.join(DIST, "assets")), name="assets")

    @app.get("/{full_path:path}")
    async def spa(full_path: str):
        index = os.path.join(DIST, "index.html")
        return FileResponse(index)
