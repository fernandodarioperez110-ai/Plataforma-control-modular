import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useStore } from "../store.jsx";
import { wsUrl } from "../api.js";
import StepBar from "../components/StepBar.jsx";
import Scope from "../components/Scope.jsx";

const EMPTY_TEL = { t: 0, ref: 0, vc: 0, error: 0, u: 0 };

export default function Control() {
  const nav = useNavigate();
  const { ready, controladorDef, prototipo, controlador, params, setParams } = useStore();

  const [running, setRunning] = useState(false);
  const [data, setData] = useState([]);       // historial de telemetría
  const [last, setLast] = useState(EMPTY_TEL);
  const [finished, setFinished] = useState(null); // {reason, aviso, metrics, run_id}
  const [falla, setFalla] = useState(null);       // mensaje de error de conexión
  const wsRef = useRef(null);
  const cerradoBienRef = useRef(false);           // true si la corrida terminó con "done" o "error"

  useEffect(() => {
    if (!ready) nav("/");
  }, [ready, nav]);

  useEffect(() => () => wsRef.current?.close(), []);

  if (!controladorDef) return null;

  // Validación: todos los campos con número válido dentro de rango
  const validate = (key, raw) => {
    const def = controladorDef.params.find((p) => p.key === key);
    if (raw === "" || raw === "-" || isNaN(Number(raw))) return false;
    const v = Number(raw);
    if (def.min !== undefined && v < def.min) return false;
    if (def.max !== undefined && v > def.max) return false;
    return true;
  };
  const allValid = controladorDef.params.every((p) => validate(p.key, params[p.key]));

  const onChange = (key, val) => setParams({ ...params, [key]: val });

  // Agrupa parámetros consecutivos que comparten "grupo" (p. ej. los 7
  // valores de E_PICOS) para pintarlos como una fila tipo matriz, igual a
  // como se ven los arreglos { a, b, c, ... } en Arduino IDE. Los params
  // sin "grupo" (setpoint, kp, etc.) se quedan como campos normales.
  const filas = [];
  controladorDef.params.forEach((p) => {
    if (p.grupo) {
      const ultima = filas[filas.length - 1];
      if (ultima && ultima.tipo === "grupo" && ultima.grupo === p.grupo) {
        ultima.items.push(p);
      } else {
        filas.push({ tipo: "grupo", grupo: p.grupo, items: [p] });
      }
    } else {
      filas.push({ tipo: "campo", p });
    }
  });

  const start = () => {
    setData([]); setLast(EMPTY_TEL); setFinished(null); setFalla(null);
    cerradoBienRef.current = false;
    const ws = new WebSocket(wsUrl());
    wsRef.current = ws;
    ws.onopen = () => {
      const numeric = {};
      controladorDef.params.forEach((p) => (numeric[p.key] = Number(params[p.key])));
      ws.send(JSON.stringify({ prototipo, controlador, params: numeric }));
      setRunning(true);
    };
    ws.onmessage = (ev) => {
      const m = JSON.parse(ev.data);
      if (m.type === "telemetry") {
        setLast(m);
        setData((d) => [...d, m]);
      } else if (m.type === "done") {
        cerradoBienRef.current = true;
        setRunning(false);
        setFinished({ reason: m.reason, aviso: m.aviso, metrics: m.metrics, run_id: m.run_id });
        ws.close();
      } else if (m.type === "error") {
        // p. ej. no se pudo conectar con el ESP32 (red WiFi equivocada)
        cerradoBienRef.current = true;
        setRunning(false);
        setFalla(m.message || "Ocurrió un error en el backend.");
        ws.close();
      }
    };
    ws.onerror = () => {
      if (cerradoBienRef.current) return;
      cerradoBienRef.current = true;
      setRunning(false);
      setFalla("No se pudo conectar con el backend. ¿Está corriendo en el puerto 8000?");
    };
    ws.onclose = () => {
      // Si la conexión se cerró sin aviso, se libera la pantalla en vez de
      // quedarse en "ADQUIRIENDO" para siempre.
      if (cerradoBienRef.current) return;
      cerradoBienRef.current = true;
      setRunning(false);
      setFalla("Se perdió la conexión con el backend durante la corrida.");
    };
  };

  const finalizar = () => {
    const ws = wsRef.current;
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ action: "stop" }));
    } else {
      setRunning(false);   // la conexión ya no existe: solo se libera la pantalla
    }
  };

  const reasonText = finished?.reason === "setpoint"
    ? "El sistema alcanzó el setpoint y se estabilizó."
    : finished?.reason === "timeout"
    ? "Se alcanzó el tope de duración sin estabilizar por completo."
    : finished?.reason === "tiempo"
    ? "Se completó el tiempo de la corrida."
    : finished?.reason === "linea"
    ? "El carrito perdió la línea por más de 1 s (se salió de la pista) y se detuvo."
    : finished?.reason === "conexion"
    ? `Se perdió la conexión con el ESP32 a mitad de la corrida. ${finished.aviso || ""} Se guardaron los datos que alcanzaron a llegar.`
    : "El proceso fue detenido manualmente.";

  return (
    <>
      <StepBar current="/control" />
      <div className="page">
        <div className="page-head">
          <h1>Control en tiempo real</h1>
          <p>Ingresa los parámetros del controlador {controladorDef.nombre}. Al iniciar verás la respuesta del prototipo en vivo.</p>
        </div>

        <div className="control-grid">
          {/* Formulario */}
          <div className="panel">
            <h2>Parámetros · {controladorDef.nombre}</h2>
            {filas.map((fila, i) => {
              if (fila.tipo === "campo") {
                const p = fila.p;
                const bad = params[p.key] !== "" && !validate(p.key, params[p.key]);
                return (
                  <div className="field" key={p.key}>
                    <label>
                      {p.label}
                      {p.unidad ? <span className="u">{p.unidad}</span> : null}
                    </label>
                    <input
                      type="number"
                      className={bad ? "bad" : ""}
                      value={params[p.key] ?? "0"}
                      disabled={running}
                      onChange={(e) => onChange(p.key, e.target.value)}
                    />
                    {bad && (
                      <div className="hint">
                        Rango {p.min ?? "-∞"} a {p.max ?? "∞"}
                      </div>
                    )}
                  </div>
                );
              }
              // Fila tipo matriz: los 7 valores de un grupo (E_PICOS, DE_PICOS, SALIDA_PICOS)
              const primero = fila.items[0];
              const algunoMalo = fila.items.some(
                (p) => params[p.key] !== "" && !validate(p.key, params[p.key])
              );
              return (
                <div className="field" key={fila.grupo}>
                  <label>
                    {primero.grupo_label}
                    {primero.grupo_unidad ? <span className="u">{primero.grupo_unidad}</span> : null}
                  </label>
                  <div className="matrix-row">
                    <span className="brace">{"{"}</span>
                    {fila.items.map((p, idx) => {
                      const bad = params[p.key] !== "" && !validate(p.key, params[p.key]);
                      return (
                        <span className="matrix-cell" key={p.key}>
                          <input
                            type="number"
                            title={p.label}
                            className={bad ? "bad" : ""}
                            value={params[p.key] ?? "0"}
                            disabled={running}
                            onChange={(e) => onChange(p.key, e.target.value)}
                          />
                          {idx < fila.items.length - 1 && <span className="comma">,</span>}
                        </span>
                      );
                    })}
                    <span className="brace">{"}"}</span>
                  </div>
                  <div className="matrix-labels">
                    {fila.items.map((p) => (
                      <span key={p.key}>{p.label}</span>
                    ))}
                  </div>
                  {algunoMalo && <div className="hint">Revisa los valores fuera de rango.</div>}
                </div>
              );
            })}

            <div className="start-slot">
              {!running && allValid && (
                <button className="btn primary block fade-in" onClick={start}>
                  Iniciar
                </button>
              )}
              {running && (
                <button className="btn danger block" onClick={finalizar}>
                  Finalizar
                </button>
              )}
              {!running && !allValid && (
                <p style={{ fontSize: 12.5, color: "var(--ink-faint)", fontFamily: "var(--f-mono)", margin: 0 }}>
                  Completa todos los campos para iniciar.
                </p>
              )}
            </div>
          </div>

          {/* Osciloscopio + lecturas */}
          <div>
            <div className="scope-wrap">
              <div className="scope-head">
                <span className="title">Respuesta del sistema</span>
                <span className={`status ${running ? "live" : ""}`}>
                  <span className="led" />
                  {running ? "ADQUIRIENDO" : finished ? "DETENIDO" : "EN ESPERA"}
                </span>
              </div>
              <div className="legend">
                <span><i style={{ background: "#e8a33d" }} />Referencia</span>
                <span><i style={{ background: "#12b5ac" }} />Variable controlada</span>
                <span><i style={{ background: "#e5484d" }} />Error</span>
                <span><i style={{ background: "#5b8cf5" }} />Señal de control</span>
              </div>
              <Scope data={data} />
              <div className="readouts">
                <Readout k="Referencia" v={last.ref} />
                <Readout k="Var. controlada" v={last.vc} />
                <Readout k="Error" v={last.error} color="var(--sig-err)" />
                <Readout k="Señal control" v={last.u} color="var(--sig-u)" />
                <Readout k="Tiempo" v={last.t} unit="s" />
              </div>
            </div>
          </div>
        </div>
      </div>

      {finished && (
        <div className="overlay">
          <div className="modal">
            <span className="warn-badge">
              {finished.reason === "conexion" ? "⚠ CONEXIÓN PERDIDA" : "⚠ PROCESO FINALIZADO"}
            </span>
            <h3>Corrida completada</h3>
            <p>{reasonText}</p>
            <div className="mini-metrics">
              <div><div className="k">Tiempo de ejecución</div><div className="v">{finished.metrics.tiempo_ejecucion} s</div></div>
              <div><div className="k">Error RMS</div><div className="v">{finished.metrics.error_rms}</div></div>
              <div><div className="k">Sobreimpulso</div><div className="v">{finished.metrics.sobreimpulso} %</div></div>
              <div><div className="k">Error estacionario</div><div className="v">{finished.metrics.error_estacionario}</div></div>
            </div>
            <div className="actions-row">
              <button className="btn ghost" onClick={() => setFinished(null)}>Cerrar</button>
              <button className="btn primary" onClick={() => nav("/datos")}>Continuar a datos</button>
            </div>
          </div>
        </div>
      )}

      {falla && (
        <div className="overlay">
          <div className="modal">
            <span className="warn-badge">⚠ ERROR DE CONEXIÓN</span>
            <h3>No se pudo completar la corrida</h3>
            <p>{falla}</p>
            <div className="actions-row">
              <button className="btn primary" onClick={() => setFalla(null)}>Entendido</button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

function Readout({ k, v, unit = "", color }) {
  const num = typeof v === "number" ? v.toFixed(2) : v;
  return (
    <div className="readout">
      <div className="k">{k}</div>
      <div className="v" style={{ color: color || "var(--panel-ink)" }}>
        {num}<span style={{ fontSize: 12, color: "#6d8480" }}>{unit ? " " + unit : ""}</span>
      </div>
    </div>
  );
}
