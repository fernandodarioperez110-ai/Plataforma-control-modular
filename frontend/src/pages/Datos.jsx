import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  LineChart, Line, BarChart, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip, Legend, ResponsiveContainer,
} from "recharts";
import { fetchLogs, fetchRun, deleteRuns } from "../api.js";
import StepBar from "../components/StepBar.jsx";

const METRICAS = [
  { key: "tiempo_ejecucion", label: "Tiempo ejec. (s)" },
  { key: "error_rms", label: "Error RMS" },
  { key: "sobreimpulso", label: "Sobreimpulso (%)" },
  { key: "error_estacionario", label: "Error estac." },
];

export default function Datos() {
  const nav = useNavigate();
  const [logs, setLogs] = useState(null);
  const [selId, setSelId] = useState(null);
  const [run, setRun] = useState(null);
  const [metrica, setMetrica] = useState("error_rms");
  const [checked, setChecked] = useState(() => new Set());
  const [confirmando, setConfirmando] = useState(false);
  const [borrando, setBorrando] = useState(false);

  useEffect(() => {
    fetchLogs().then((l) => {
      setLogs(l);
      if (l.length) selectRun(l[0].id);
    });
  }, []);

  const selectRun = (id) => {
    setSelId(id);
    fetchRun(id).then(setRun);
  };

  const toggleChecked = (id) => {
    setChecked((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const toggleCheckedAll = () => {
    setChecked((prev) => {
      if (logs && prev.size === logs.length) return new Set();
      return new Set(logs.map((r) => r.id));
    });
  };

  const eliminarSeleccionados = async () => {
    setBorrando(true);
    try {
      const ids = Array.from(checked);
      await deleteRuns(ids);
      const restantes = await fetchLogs();
      setLogs(restantes);
      setChecked(new Set());
      if (ids.includes(selId)) {
        if (restantes.length) selectRun(restantes[0].id);
        else { setSelId(null); setRun(null); }
      }
    } finally {
      setBorrando(false);
      setConfirmando(false);
    }
  };

  // Serie de telemetría del run seleccionado (submuestreada para el gráfico)
  const serie = useMemo(() => {
    if (!run) return [];
    const { t, ref, vc, error } = run.telemetria;
    const paso = Math.max(1, Math.floor(t.length / 300));
    const out = [];
    for (let i = 0; i < t.length; i += paso) {
      out.push({ t: t[i], Referencia: ref[i], "Var. controlada": vc[i], Error: error[i] });
    }
    return out;
  }, [run]);

  const comparativa = useMemo(() => {
    if (!logs) return [];
    return logs.slice(0, 12).reverse().map((r) => ({
      run: `#${r.id}`,
      valor: r[metrica],
      ctrl: r.controlador,
    }));
  }, [logs, metrica]);

  if (!logs) {
    return (<><StepBar current="/datos" /><div className="page"><div className="empty">Cargando registros…</div></div></>);
  }

  if (logs.length === 0) {
    return (
      <>
        <StepBar current="/datos" />
        <div className="page">
          <div className="empty">
            <div className="big">Aún no hay corridas registradas</div>
            <p>Ejecuta un controlador para generar tu primer registro.</p>
            <div className="actions-row" style={{ justifyContent: "center", marginTop: 16 }}>
              <button className="btn primary" onClick={() => nav("/")}>Ir a selección</button>
            </div>
          </div>
        </div>
      </>
    );
  }

  return (
    <>
      <StepBar current="/datos" />
      <div className="page">
        <div className="page-head" style={{ display: "flex", alignItems: "flex-end", justifyContent: "space-between", gap: 16 }}>
          <div>
            <h1>Registros y análisis</h1>
            <p>Últimas {logs.length} corridas (máx. 50). Selecciona una fila para graficar su respuesta.</p>
          </div>
          <button
            className="btn danger"
            disabled={checked.size === 0}
            onClick={() => setConfirmando(true)}
          >
            Eliminar registro{checked.size > 1 ? "s" : ""}{checked.size > 0 ? ` (${checked.size})` : ""}
          </button>
        </div>

        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th style={{ width: 34 }}>
                  <input
                    type="checkbox"
                    checked={logs.length > 0 && checked.size === logs.length}
                    onChange={toggleCheckedAll}
                  />
                </th>
                <th>ID</th><th>Fecha</th><th>Prototipo</th><th>Controlador</th>
                <th>Tiempo ejec.</th><th>Error RMS</th><th>Sobreimpulso</th><th>Error estac.</th>
              </tr>
            </thead>
            <tbody>
              {logs.map((r) => (
                <tr key={r.id} className={selId === r.id ? "sel" : ""} onClick={() => selectRun(r.id)}>
                  <td onClick={(e) => e.stopPropagation()}>
                    <input
                      type="checkbox"
                      checked={checked.has(r.id)}
                      onChange={() => toggleChecked(r.id)}
                    />
                  </td>
                  <td className="mono">{r.id}</td>
                  <td className="mono" style={{ color: "var(--ink-soft)" }}>{r.creado.replace("T", " ")}</td>
                  <td><span className="pill">{r.prototipo}</span></td>
                  <td><span className="pill">{r.controlador}</span></td>
                  <td className="mono">{r.tiempo_ejecucion} s</td>
                  <td className="mono">{r.error_rms}</td>
                  <td className="mono">{r.sobreimpulso} %</td>
                  <td className="mono">{r.error_estacionario}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {confirmando && (
          <div className="overlay" onClick={() => !borrando && setConfirmando(false)}>
            <div className="modal" onClick={(e) => e.stopPropagation()}>
              <span className="warn-badge">⚠ ACCIÓN IRREVERSIBLE</span>
              <h3>¿Eliminar {checked.size} registro{checked.size > 1 ? "s" : ""}?</h3>
              <p>Esta acción borra la(s) corrida(s) seleccionada(s) de forma permanente y no se puede deshacer.</p>
              <div className="actions-row">
                <button className="btn ghost" disabled={borrando} onClick={() => setConfirmando(false)}>Cancelar</button>
                <button className="btn danger" disabled={borrando} onClick={eliminarSeleccionados}>
                  {borrando ? "Eliminando…" : "Sí, eliminar"}
                </button>
              </div>
            </div>
          </div>
        )}

        {run && (
          <div className="chart-card">
            <h3>Respuesta temporal — corrida #{run.id}</h3>
            <p className="sub">{run.prototipo} · {run.controlador} · setpoint {run.params.setpoint ?? 0}</p>
            <ResponsiveContainer width="100%" height={280}>
              <LineChart data={serie} margin={{ top: 6, right: 16, bottom: 4, left: -8 }}>
                <CartesianGrid stroke="#e6ebee" />
                <XAxis dataKey="t" tick={{ fontSize: 11, fontFamily: "IBM Plex Mono" }} stroke="#8b959c"
                  label={{ value: "t (s)", position: "insideBottomRight", offset: -2, fontSize: 11 }} />
                <YAxis tick={{ fontSize: 11, fontFamily: "IBM Plex Mono" }} stroke="#8b959c" />
                <Tooltip contentStyle={{ fontFamily: "IBM Plex Mono", fontSize: 12, borderRadius: 8 }} />
                <Legend wrapperStyle={{ fontSize: 12 }} />
                <Line type="monotone" dataKey="Referencia" stroke="#e8a33d" strokeDasharray="5 4" dot={false} strokeWidth={1.6} />
                <Line type="monotone" dataKey="Var. controlada" stroke="#12b5ac" dot={false} strokeWidth={2.2} />
                <Line type="monotone" dataKey="Error" stroke="#e5484d" dot={false} strokeWidth={1.4} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        )}

        <div className="chart-card">
          <h3>Comparación entre corridas</h3>
          <p className="sub">Métrica seleccionada por registro (últimas 12)</p>
          <div className="toggle-row">
            {METRICAS.map((m) => (
              <button key={m.key} className={`toggle ${metrica === m.key ? "on" : ""}`} onClick={() => setMetrica(m.key)}>
                {m.label}
              </button>
            ))}
          </div>
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={comparativa} margin={{ top: 6, right: 16, bottom: 4, left: -8 }}>
              <CartesianGrid stroke="#e6ebee" vertical={false} />
              <XAxis dataKey="run" tick={{ fontSize: 11, fontFamily: "IBM Plex Mono" }} stroke="#8b959c" />
              <YAxis tick={{ fontSize: 11, fontFamily: "IBM Plex Mono" }} stroke="#8b959c" />
              <Tooltip contentStyle={{ fontFamily: "IBM Plex Mono", fontSize: 12, borderRadius: 8 }} cursor={{ fill: "rgba(18,181,172,0.06)" }} />
              <Bar dataKey="valor" fill="#12b5ac" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>
    </>
  );
}
