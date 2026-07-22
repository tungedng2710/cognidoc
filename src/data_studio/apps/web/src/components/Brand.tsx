import { Layers3 } from "lucide-react";
import { Link } from "react-router-dom";

export function Brand() {
  return (
    <Link to="/" className="flex items-center gap-3" aria-label="CogniDoc Data Studio home">
      <span className="grid size-9 place-items-center rounded-xl bg-teal-900 text-amber-200 shadow-sm">
        <Layers3 className="size-5" aria-hidden="true" />
      </span>
      <span>
        <span className="block text-sm font-bold tracking-tight text-slate-950">CogniDoc</span>
        <span className="block text-[10px] font-semibold tracking-[0.18em] text-slate-500 uppercase">
          Data Studio
        </span>
      </span>
    </Link>
  );
}

