import { createContext, useContext, useEffect, useState } from "react";
import { fetchMeta } from "./api.js";

const StoreCtx = createContext(null);

export function StoreProvider({ children }) {
  const [meta, setMeta] = useState(null);
  const [error, setError] = useState(null);

  const [prototipo, setPrototipo] = useState(null);   // id
  const [controlador, setControlador] = useState(null); // id
  const [params, setParams] = useState({});           // { key: valor }

  useEffect(() => {
    fetchMeta().then(setMeta).catch((e) => setError(e.message));
  }, []);

  // Cada prototipo tiene sus propios controladores (el carrito usa los
  // parámetros de sus .ino, distintos a los del balancín).
  const listaDe = (protoId) =>
    meta?.controladores_por_prototipo?.[protoId] || meta?.controladores || [];
  const controladores = listaDe(prototipo);

  const controladorDef = controladores.find((c) => c.id === controlador) || null;
  const prototipoDef = meta?.prototipos.find((p) => p.id === prototipo) || null;

  // Inicializa los parámetros con su valor por defecto (el mismo que tenías
  // en el .ino individual) al elegir un controlador.
  function initParams(protoId, ctrlId) {
    const def = listaDe(protoId).find((c) => c.id === ctrlId);
    const init = {};
    def?.params.forEach((p) => (init[p.key] = String(p.default ?? 0)));
    setParams(init);
  }

  function chooseControlador(id) {
    setControlador(id);
    initParams(prototipo, id);
  }

  // Al cambiar de prototipo se recargan los parámetros del controlador ya
  // elegido con los valores por defecto de ESE prototipo.
  function choosePrototipo(id) {
    setPrototipo(id);
    if (controlador) initParams(id, controlador);
  }

  const value = {
    meta, error,
    prototipo, setPrototipo: choosePrototipo,
    controladores,
    controlador, chooseControlador,
    controladorDef, prototipoDef,
    params, setParams,
    ready: Boolean(prototipo && controlador),
  };
  return <StoreCtx.Provider value={value}>{children}</StoreCtx.Provider>;
}

export const useStore = () => useContext(StoreCtx);
