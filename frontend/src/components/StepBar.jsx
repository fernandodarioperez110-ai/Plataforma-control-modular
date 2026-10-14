import { NavLink } from "react-router-dom";
import { useStore } from "../store.jsx";

const STEPS = [
  { to: "/", num: "01", lbl: "Selección" },
  { to: "/control", num: "02", lbl: "Control" },
  { to: "/datos", num: "03", lbl: "Datos" },
];

export default function StepBar({ current }) {
  const { ready } = useStore();
  return (
    <nav className="steps">
      {STEPS.map((s) => {
        const disabled = s.to === "/control" && !ready;
        const cls = [
          "step",
          current === s.to ? "active" : "",
          disabled ? "disabled" : "",
        ].join(" ");
        return (
          <NavLink key={s.to} to={disabled ? "#" : s.to} className={cls} end>
            <span className="num">{s.num}</span>
            <span className="lbl">{s.lbl}</span>
          </NavLink>
        );
      })}
    </nav>
  );
}
