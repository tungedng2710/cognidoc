import { BookOpenText } from "lucide-react";
import { Link } from "react-router-dom";

export function ApiGuideLink() {
  return (
    <Link
      aria-label="API guide"
      className="inline-flex min-h-9 items-center gap-2 rounded-xl border border-white/15 px-3 text-xs font-semibold text-slate-200 transition hover:bg-white/10 hover:text-white"
      to="/docs/api"
    >
      <BookOpenText className="size-4" />
      <span className="hidden sm:inline">API guide</span>
    </Link>
  );
}
