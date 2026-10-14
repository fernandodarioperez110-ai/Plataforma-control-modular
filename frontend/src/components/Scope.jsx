import { useEffect, useRef } from "react";

const COLORS = {
  ref: "#e8a33d",
  vc: "#12b5ac",
  error: "#e5484d",
  u: "#5b8cf5",
};
const WINDOW = 420; // muestras visibles (~12.6 s a 33 Hz)

// Dibuja un osciloscopio con las cuatro trazas y rejilla, auto-escalando Y.
export default function Scope({ data }) {
  const canvasRef = useRef(null);

  useEffect(() => {
    const cv = canvasRef.current;
    if (!cv) return;
    const dpr = window.devicePixelRatio || 1;
    const W = cv.clientWidth, H = cv.clientHeight;
    cv.width = W * dpr; cv.height = H * dpr;
    const ctx = cv.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, W, H);

    const pad = { l: 44, r: 12, t: 12, b: 22 };
    const gw = W - pad.l - pad.r, gh = H - pad.t - pad.b;

    // rejilla
    ctx.strokeStyle = "rgba(120,200,195,0.12)";
    ctx.lineWidth = 1;
    ctx.font = "10px 'IBM Plex Mono', monospace";
    ctx.fillStyle = "#5f7571";
    const win = data.slice(-WINDOW);

    // escala Y a partir de ref, vc, u (error se muestra en su propia magnitud)
    let ymin = Infinity, ymax = -Infinity;
    win.forEach((d) => {
      [d.ref, d.vc, d.error, d.u].forEach((v) => {
        if (v < ymin) ymin = v;
        if (v > ymax) ymax = v;
      });
    });
    if (!isFinite(ymin)) { ymin = -1; ymax = 1; }
    if (ymin === ymax) { ymin -= 1; ymax += 1; }
    const span = ymax - ymin;
    ymin -= span * 0.1; ymax += span * 0.1;

    const yPix = (v) => pad.t + gh - ((v - ymin) / (ymax - ymin)) * gh;
    const xPix = (i) => pad.l + (win.length <= 1 ? 0 : (i / (win.length - 1)) * gw);

    // rejilla horizontal + etiquetas Y
    for (let r = 0; r <= 4; r++) {
      const y = pad.t + (r / 4) * gh;
      ctx.beginPath(); ctx.moveTo(pad.l, y); ctx.lineTo(W - pad.r, y); ctx.stroke();
      const val = ymax - (r / 4) * (ymax - ymin);
      ctx.fillText(val.toFixed(1), 6, y + 3);
    }
    // línea de cero
    if (ymin < 0 && ymax > 0) {
      ctx.strokeStyle = "rgba(120,200,195,0.28)";
      const zy = yPix(0);
      ctx.beginPath(); ctx.moveTo(pad.l, zy); ctx.lineTo(W - pad.r, zy); ctx.stroke();
    }

    if (win.length < 2) return;

    const drawTrace = (key, color, width, dashed) => {
      ctx.strokeStyle = color; ctx.lineWidth = width;
      ctx.setLineDash(dashed ? [5, 4] : []);
      ctx.beginPath();
      win.forEach((d, i) => {
        const x = xPix(i), y = yPix(d[key]);
        i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
      });
      ctx.stroke();
      ctx.setLineDash([]);
    };

    drawTrace("u", COLORS.u, 1.3, false);
    drawTrace("error", COLORS.error, 1.3, false);
    drawTrace("ref", COLORS.ref, 1.4, true);
    drawTrace("vc", COLORS.vc, 2, false);

    // eje X: tiempo
    const t0 = win[0].t, t1 = win[win.length - 1].t;
    ctx.fillStyle = "#5f7571";
    ctx.fillText(`${t0.toFixed(1)} s`, pad.l, H - 6);
    ctx.fillText(`${t1.toFixed(1)} s`, W - pad.r - 34, H - 6);
  }, [data]);

  return (
    <div style={{ height: 300, background: "var(--panel-2)" }}>
      <canvas ref={canvasRef} style={{ width: "100%", height: "100%", display: "block" }} />
    </div>
  );
}
