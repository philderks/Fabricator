import { Link, useRouter } from "@tanstack/react-router";
import { type MouseEvent, type ReactNode, useEffect, useState } from "react";
import { navItems, type ActivePage, type MarketingHomeSection } from "../data";

export function MarketingLayout({
  active,
  legal = false,
  children,
}: {
  active: ActivePage;
  legal?: boolean;
  children: ReactNode;
}) {
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const activeSection = useActiveMarketingSection(active);

  return (
    <div className="relative isolate min-h-screen overflow-hidden bg-[#0b0b0b] text-white">
      <div
        className="fabricator-site-bg pointer-events-none fixed inset-0 z-0"
        aria-hidden="true"
      />
      <header className="sticky top-0 z-40 border-b border-white/10 bg-[#0f0f0f]/85 backdrop-blur-xl">
        <nav className="mx-auto flex min-h-20 max-w-6xl flex-wrap items-center justify-between px-5">
          <MarketingRouteLink
            href="/"
            className="flex items-center gap-3 font-semibold text-white"
            ariaLabel="Fabricator home"
          >
            <FabricatorMark />
            <span>Fabricator</span>
          </MarketingRouteLink>
          <div className="hidden items-center gap-2 md:flex">
            {navItems.map((item) => (
              <NavLink
                key={item.label}
                item={item}
                active={active}
                activeSection={activeSection}
              />
            ))}
          </div>
          <button
            type="button"
            aria-label={
              mobileMenuOpen ? "Close navigation menu" : "Open navigation menu"
            }
            aria-expanded={mobileMenuOpen}
            aria-controls="marketing-mobile-menu"
            onClick={() => setMobileMenuOpen((current) => !current)}
            className="group inline-flex h-11 w-11 items-center justify-center rounded-md border border-white/10 bg-white/[0.04] text-white shadow-none transition hover:border-primary/45 hover:bg-primary/10 focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-primary/40 md:hidden"
          >
            <span className="relative h-5 w-6" aria-hidden="true">
              <span
                className={`absolute left-0 top-0 h-0.5 w-6 rounded-full bg-current transition duration-200 ease-out ${mobileMenuOpen ? "translate-y-2 rotate-45" : "translate-y-0 rotate-0"}`}
              />
              <span
                className={`absolute left-0 top-2 h-0.5 w-6 rounded-full bg-current transition duration-200 ease-out ${mobileMenuOpen ? "opacity-0" : "opacity-100"}`}
              />
              <span
                className={`absolute left-0 top-4 h-0.5 w-6 rounded-full bg-current transition duration-200 ease-out ${mobileMenuOpen ? "-translate-y-2 -rotate-45" : "translate-y-0 rotate-0"}`}
              />
            </span>
          </button>
          <div
            id="marketing-mobile-menu"
            className={`grid w-full transition-[grid-template-rows,opacity] duration-200 ease-out md:hidden ${
              mobileMenuOpen
                ? "grid-rows-[1fr] opacity-100"
                : "grid-rows-[0fr] opacity-0"
            }`}
          >
            <div className="overflow-hidden">
              <div className="mb-4 mt-4 grid gap-2 rounded-xl border border-white/10 bg-[#171717]/95 p-2 shadow-2xl shadow-black/40">
                {navItems.map((item) => (
                  <NavLink
                    key={item.label}
                    item={item}
                    active={active}
                    activeSection={activeSection}
                    variant="mobile"
                    onNavigate={() => setMobileMenuOpen(false)}
                  />
                ))}
              </div>
            </div>
          </div>
        </nav>
      </header>

      <main className="relative z-10">{children}</main>

      <footer
        className={`relative z-10 ${legal ? "border-t border-white/10 bg-[#0b0b0b]/80" : "border-t border-white/10 bg-[#080808]/80"}`}
      >
        <div className="mx-auto flex max-w-6xl flex-col gap-4 px-5 py-8 text-sm text-zinc-500 md:flex-row md:items-center md:justify-between">
          <p>© 2026 Fabricator</p>
          <div className="flex gap-5">
            <Link to="/privacy" className="hover:text-orange-300">
              Privacy Policy
            </Link>
            <Link to="/impressum" className="hover:text-orange-300">
              Legal Notice
            </Link>
          </div>
        </div>
      </footer>
    </div>
  );
}

function useActiveMarketingSection(active: ActivePage): MarketingHomeSection {
  const [activeSection, setActiveSection] = useState<MarketingHomeSection>(() =>
    getHashSection()
  );

  useEffect(() => {
    if (active !== "home") {
      setActiveSection(null);
      return;
    }

    const updateActiveSection = () => {
      const sectionIds = ["how", "shots", "faq"] as const;
      const current = sectionIds.reduce<MarketingHomeSection>(
        (visibleSection, sectionId) => {
          const section = document.getElementById(sectionId);
          if (!section) return visibleSection;

          const sectionTop = section.getBoundingClientRect().top;
          return sectionTop <= 180 ? sectionId : visibleSection;
        },
        null
      );

      setActiveSection(current ?? getHashSection());
    };

    updateActiveSection();
    window.addEventListener("scroll", updateActiveSection, { passive: true });
    window.addEventListener("hashchange", updateActiveSection);
    window.addEventListener("resize", updateActiveSection);

    return () => {
      window.removeEventListener("scroll", updateActiveSection);
      window.removeEventListener("hashchange", updateActiveSection);
      window.removeEventListener("resize", updateActiveSection);
    };
  }, [active]);

  return activeSection;
}

function getHashSection(): MarketingHomeSection {
  if (typeof window === "undefined") return null;

  const hash = window.location.hash.slice(1);
  return hash === "how" || hash === "shots" || hash === "faq" ? hash : null;
}

function NavLink({
  item,
  active,
  activeSection,
  variant = "desktop",
  onNavigate,
}: {
  item: (typeof navItems)[number];
  active: ActivePage;
  activeSection: MarketingHomeSection;
  variant?: "desktop" | "mobile";
  onNavigate?: () => void;
}) {
  const router = useRouter();
  const hashSection = item.href.startsWith("/#") ? item.href.slice(2) : null;
  const isActive = hashSection
    ? active === "home" && activeSection === hashSection
    : item.active === active;
  const activeUnderline = isActive
    ? "after:absolute after:left-3 after:right-3 after:-bottom-2 after:h-0.5 after:rounded-full after:bg-primary after:shadow-[0_0_12px_rgba(249,115,22,0.55)]"
    : "after:absolute after:left-3 after:right-3 after:-bottom-2 after:h-0.5 after:rounded-full after:bg-primary after:opacity-0 after:transition-opacity hover:after:opacity-35";
  const className =
    variant === "mobile"
      ? `relative flex min-h-12 items-center justify-between rounded-lg border px-4 text-sm font-semibold transition ${
          isActive
            ? "border-primary/45 bg-primary/15 text-white shadow-[inset_3px_0_0_var(--primary)]"
            : "border-transparent text-zinc-300 hover:border-white/10 hover:bg-white/[0.05] hover:text-white"
        } ${item.cta ? "bg-primary text-primary-foreground hover:bg-orange-400 hover:text-primary-foreground" : ""}`
      : item.cta
        ? `relative rounded-md border px-4 py-2 text-sm font-semibold transition ${activeUnderline} ${active === "download" ? "border-orange-400 bg-orange-500 text-black" : "border-orange-500/40 bg-orange-500/15 text-orange-100 hover:bg-orange-500/25"}`
        : `relative rounded-md px-3 py-2 text-sm font-medium transition ${activeUnderline} ${isActive ? "text-white" : "text-zinc-400 hover:text-white"}`;

  const handleClick = (event: MouseEvent<HTMLAnchorElement>) => {
    if (
      variant === "mobile" &&
      item.href.startsWith("/#") &&
      typeof window !== "undefined" &&
      window.location.pathname === "/"
    ) {
      event.preventDefault();
      onNavigate?.();
      window.setTimeout(() => {
        void navigateMarketing(router, item.href);
      }, 210);
      return;
    }

    handleMarketingNavigation(event, router, item.href);
    onNavigate?.();
  };

  return (
    <a href={item.href} className={className} onClick={handleClick}>
      <span>{item.label}</span>
      {variant === "mobile" && isActive ? (
        <span className="h-2 w-2 rounded-full bg-primary" aria-hidden="true" />
      ) : null}
    </a>
  );
}

export function MarketingRouteLink({
  href,
  className,
  children,
  ariaLabel,
}: {
  href: string;
  className?: string;
  children: ReactNode;
  ariaLabel?: string;
}) {
  const router = useRouter();

  return (
    <a
      href={href}
      aria-label={ariaLabel}
      className={className}
      onClick={(event) => handleMarketingNavigation(event, router, href)}
    >
      {children}
    </a>
  );
}

type MarketingRouter = ReturnType<typeof useRouter>;

function handleMarketingNavigation(
  event: MouseEvent<HTMLAnchorElement>,
  router: MarketingRouter,
  href: string
) {
  if (
    event.defaultPrevented ||
    event.button !== 0 ||
    event.metaKey ||
    event.altKey ||
    event.ctrlKey ||
    event.shiftKey
  ) {
    return;
  }

  if (!href.startsWith("/")) {
    return;
  }

  event.preventDefault();
  void navigateMarketing(router, href);
}

async function navigateMarketing(router: MarketingRouter, href: string) {
  if (typeof window === "undefined") return;

  const hashIndex = href.indexOf("#");
  const pathname = hashIndex >= 0 ? href.slice(0, hashIndex) || "/" : href;
  const hash = hashIndex >= 0 ? href.slice(hashIndex + 1) : "";
  const currentPathname = window.location.pathname;

  if (hash && currentPathname === pathname) {
    window.history.pushState(null, "", href);
    scrollToMarketingHash(hash, "smooth");
    return;
  }

  await withMarketingViewTransition(async () => {
    await router.navigate({ to: pathname });
  });

  if (hash) {
    window.history.replaceState(null, "", href);
    scrollToMarketingHash(hash, "auto");
  } else {
    window.scrollTo({ top: 0, behavior: "auto" });
  }
}

async function withMarketingViewTransition(callback: () => Promise<void>) {
  if (typeof document === "undefined" || typeof window === "undefined") {
    await callback();
    return;
  }

  const documentWithTransitions = document as Document & {
    startViewTransition?: (callback: () => Promise<void>) => {
      finished: Promise<void>;
    };
  };

  if (
    !documentWithTransitions.startViewTransition ||
    window.matchMedia("(prefers-reduced-motion: reduce)").matches
  ) {
    await callback();
    return;
  }

  await documentWithTransitions.startViewTransition(callback).finished;
}

function scrollToMarketingHash(hash: string, behavior: ScrollBehavior) {
  window.requestAnimationFrame(() => {
    const target = document.getElementById(hash);

    if (!target) return;

    target.scrollIntoView({ behavior, block: "start" });
  });
}

function FabricatorMark() {
  return (
    <img src="/favicon.svg" alt="" width={32} height={32} className="h-8 w-8" />
  );
}
