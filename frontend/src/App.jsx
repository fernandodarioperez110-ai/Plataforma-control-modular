import { Routes, Route, Navigate } from "react-router-dom";
import { useStore } from "./store.jsx";
import Seleccion from "./pages/Seleccion.jsx";
import Control from "./pages/Control.jsx";
import Datos from "./pages/Datos.jsx";

function Topbar() {
  const { prototipoDef, controladorDef } = useStore();
  return (
    <header className="topbar">
      <div className="brand">
        flujo<span>·</span>controlador
        <small>ESP32 · Control Lab</small>
      </div>
      <div className="experiment-tag">
        <span className={`dot ${prototipoDef ? "on" : ""}`} />
        Prototipo: <b>{prototipoDef?.nombre || "—"}</b>
        <span className={`dot ${controladorDef ? "on" : ""}`} />
        Controlador: <b>{controladorDef?.nombre || "—"}</b>
      </div>
    </header>
  );
}

export default function App() {
  const { error } = useStore();
  return (
    <div className="app">
      <Topbar />
      {error && (
        <div style={{ background: "#fbeaea", color: "#b3282d", padding: "10px 28px", fontFamily: "var(--f-mono)", fontSize: 13 }}>
          {error} — ¿está corriendo el backend en el puerto 8000?
        </div>
      )}
      <Routes>
        <Route path="/" element={<Seleccion />} />
        <Route path="/control" element={<Control />} />
        <Route path="/datos" element={<Datos />} />
        <Route path="*" element={<Navigate to="/" />} />
      </Routes>
    </div>
  );
}
