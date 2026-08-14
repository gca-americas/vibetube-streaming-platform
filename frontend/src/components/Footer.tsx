import { ArrowUpRight } from "lucide-react";

/**
 * Site footer, shown on the gate, the showroom, and the empty-code page.
 *
 * CHANGE ME: showrooms are provisioned by an admin running backend/admin.py,
 * so there is no self-serve signup to link to. This address is where the
 * "host your own showroom" enquiries land -- point it at whichever inbox or
 * internal form your team actually watches.
 */
const HOST_CONTACT = "mailto:showrooms@example.com?subject=Vibetube%20showroom%20request";

export const Footer = () => (
  <footer className="relative z-10 w-full border-t border-hairline mt-20">
    <div className="max-w-7xl mx-auto px-4 md:px-8 py-8 flex flex-col md:flex-row items-center justify-between gap-6 text-center md:text-left">
      <div className="flex flex-col gap-1">
        <p className="text-sm font-bold text-fg">
          Google Global Advocacy Americas
        </p>
        <p className="text-xs text-fg-muted">
          © {new Date().getFullYear()} Vibetube — every showroom, its own stage.
        </p>
      </div>

      <a
        href={HOST_CONTACT}
        className="group flex items-center gap-2 px-5 py-3 rounded-2xl bg-overlay border border-hairline text-sm font-bold text-fg-muted hover:text-fg hover:border-vibe-purple/40 hover:scale-[1.03] shadow-lg hover:shadow-vibe-purple/20 transition-all duration-200"
      >
        <span>Want to host your own showroom?</span>
        <ArrowUpRight className="w-4 h-4 transition-transform duration-200 group-hover:translate-x-0.5 group-hover:-translate-y-0.5" />
      </a>
    </div>
  </footer>
);
