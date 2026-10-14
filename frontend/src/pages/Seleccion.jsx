import { useNavigate } from "react-router-dom";
import { useStore } from "../store.jsx";
import StepBar from "../components/StepBar.jsx";

export default function Seleccion() {
  const nav = useNavigate();
  const { meta, prototipo, setPrototipo, controladores, controlador, chooseControlador, ready } = useStore();

  if (!meta) {
    return (
      <>
        <StepBar current="/" />
        <div className="page"><div className="empty">Cargando configuración…</div></div>
      </>
    );
  }

  return (
    <>
      <StepBar current="/" />
      <div className="page">
        <div className="page-head">
          <h1>Configura el experimento</h1>
          <p>Elige el prototipo físico a controlar y la estrategia de control. Después definirás sus parámetros.</p>
        </div>

        <div className="section">
          <p className="eyebrow">Prototipo</p>
          <div className="grid p2">
            {meta.prototipos.map((p) => (
              <button
                key={p.id}
                className={`select-card ${prototipo === p.id ? "sel" : ""}`}
                onClick={() => setPrototipo(p.id)}
              >
                <span className="tick" />
                <h3>{p.nombre}</h3>
                <p>{p.descripcion}</p>
                <div className="unit">unidad: {p.unidad}</div>
              </button>
            ))}
          </div>
        </div>

        <div className="section">
          <p className="eyebrow">Controlador</p>
          <div className="grid p4">
            {controladores.map((c) => (
              <button
                key={c.id}
                className={`select-card ${controlador === c.id ? "sel" : ""}`}
                onClick={() => chooseControlador(c.id)}
              >
                <span className="tick" />
                <h3>{c.nombre}</h3>
                <p>{c.descripcion}</p>
                <div className="unit">{c.params.length} parámetros</div>
              </button>
            ))}
          </div>
        </div>

        <div className="actions-row">
          <button className="btn primary" disabled={!ready} onClick={() => nav("/control")}>
            Continuar
          </button>
        </div>
      </div>
    </>
  );
}
