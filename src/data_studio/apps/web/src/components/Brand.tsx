import { Link } from "react-router-dom";

const tonAiLogo =
  "https://raw.githubusercontent.com/tungedng2710/tungedng2710.github.io/main/public/assets/images/logo.png";

export function Brand() {
  return (
    <Link to="/" className="flex items-center gap-3" aria-label="TonAI Data Studio home">
      <span className="grid size-10 place-items-center overflow-hidden rounded-xl bg-gradient-to-br from-white to-slate-100 p-1 shadow-lg shadow-indigo-950/30 ring-1 ring-white/30">
        <img
          alt=""
          className="size-full object-contain"
          decoding="async"
          fetchPriority="high"
          src={tonAiLogo}
        />
      </span>
      <span>
        <span className="block text-sm font-bold tracking-tight text-white">TonAI</span>
        <span className="block text-[10px] font-semibold tracking-[0.2em] text-slate-400 uppercase">
          Data Studio
        </span>
      </span>
    </Link>
  );
}
