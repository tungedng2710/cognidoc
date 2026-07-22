import { Blocks } from "lucide-react";
import { Link } from "react-router-dom";

export function Brand() {
  return (
    <Link to="/" className="flex items-center gap-3" aria-label="CogniDoc Data Studio home">
      <span className="grid size-9 place-items-center rounded-xl bg-gradient-to-br from-indigo-500 to-cyan-400 text-white shadow-lg shadow-indigo-950/30 ring-1 ring-white/20">
        <Blocks className="size-5" aria-hidden="true" />
      </span>
      <span>
        <span className="block text-sm font-bold tracking-tight text-white">CogniDoc</span>
        <span className="block text-[10px] font-semibold tracking-[0.2em] text-slate-400 uppercase">
          Data Studio
        </span>
      </span>
    </Link>
  );
}
