import type { LucideIcon } from "lucide-react";
import { ArrowRight, Download } from "lucide-react";
import type { ReactNode } from "react";
import { MarketingRouteLink } from "./layouts/marketing-layout";

export function PageHero({
  eyebrow,
  title,
  text,
  centered = false,
}: {
  eyebrow: string;
  title: string;
  text: string;
  centered?: boolean;
}) {
  return (
    <section
      className={`mx-auto max-w-6xl px-5 py-16 md:py-24 ${centered ? "text-center" : ""}`}
    >
      <Eyebrow>{eyebrow}</Eyebrow>
      <h1
        className={`mt-4 text-4xl font-bold leading-tight md:text-6xl ${centered ? "mx-auto max-w-4xl" : "max-w-4xl"}`}
      >
        {title}
      </h1>
      <p
        className={`mt-5 text-lg leading-8 text-zinc-400 ${centered ? "mx-auto max-w-2xl" : "max-w-3xl"}`}
      >
        {text}
      </p>
      <div
        className={`mt-8 flex flex-wrap gap-3 ${centered ? "justify-center" : ""}`}
      >
        <MarketingRouteLink
          href="/download"
          className="inline-flex h-11 items-center gap-2 rounded-md bg-orange-500 px-4 text-sm font-bold text-black hover:bg-orange-400"
        >
          Download Fabricator <Download className="h-4 w-4" />
        </MarketingRouteLink>
        <MarketingRouteLink
          href="/docs"
          className="inline-flex h-11 items-center gap-2 rounded-md border border-white/10 px-4 text-sm font-semibold text-zinc-200 hover:bg-white/5"
        >
          Read the docs <ArrowRight className="h-4 w-4" />
        </MarketingRouteLink>
      </div>
    </section>
  );
}

export function Section({
  id,
  eyebrow,
  title,
  children,
}: {
  id?: string;
  eyebrow?: string;
  title?: string;
  children: ReactNode;
}) {
  return (
    <section
      id={id}
      className="mx-auto max-w-6xl scroll-mt-24 px-5 py-14 md:py-20"
    >
      {eyebrow ? <Eyebrow>{eyebrow}</Eyebrow> : null}
      {title ? (
        <h2 className="mt-3 max-w-4xl text-3xl font-bold leading-tight md:text-5xl">
          {title}
        </h2>
      ) : null}
      <div className={title || eyebrow ? "mt-8" : undefined}>{children}</div>
    </section>
  );
}

export function MiniFeature({
  icon,
  title,
  text,
}: {
  icon: LucideIcon;
  title: string;
  text: string;
}) {
  return (
    <article className="rounded-xl border border-white/10 bg-[#1b1b1b]/90 p-5 shadow-xl shadow-black/25">
      <IconBadge icon={icon} />
      <h3 className="mt-5 text-xl font-semibold">{title}</h3>
      <p className="mt-3 text-sm leading-7 text-zinc-400">{text}</p>
    </article>
  );
}

export function IconBadge({ icon: Icon }: { icon: LucideIcon }) {
  return (
    <span className="flex h-10 w-10 items-center justify-center rounded-xl border border-white/10 bg-orange-500/15 text-orange-300">
      <Icon className="h-5 w-5" />
    </span>
  );
}

export function Eyebrow({ children }: { children: ReactNode }) {
  return (
    <p className="text-xs font-black uppercase text-orange-400">{children}</p>
  );
}

export function FabricatorMark() {
  return (
    <img src="/favicon.svg" alt="" width={32} height={32} className="h-8 w-8" />
  );
}
