// Rutas relativas: en dev las resuelve el proxy de Vite; en prod las sirve FastAPI.
export async function fetchMeta() {
  const r = await fetch("/api/meta");
  if (!r.ok) throw new Error("No se pudo cargar la configuración");
  return r.json();
}

export async function fetchLogs() {
  const r = await fetch("/api/logs");
  if (!r.ok) throw new Error("No se pudieron cargar los registros");
  return r.json();
}

export async function fetchRun(id) {
  const r = await fetch(`/api/logs/${id}`);
  if (!r.ok) throw new Error("No se pudo cargar el registro");
  return r.json();
}

export async function deleteRuns(ids) {
  const r = await fetch("/api/logs", {
    method: "DELETE",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ids }),
  });
  if (!r.ok) throw new Error("No se pudieron eliminar los registros");
  return r.json();
}

export function wsUrl() {
  const proto = window.location.protocol === "https:" ? "wss" : "ws";
  return `${proto}://${window.location.host}/ws`;
}
