import { createFileRoute, Link } from "@tanstack/react-router";
import { FAQSection } from "@/components/marketing/sections/faq-section";
import {
  MarketingLayout,
  MarketingRouteLink,
} from "@/components/marketing/layouts/marketing-layout";
import { ScreenshotCarousel } from "@/components/marketing/screenshot-carousel";
import {
  Eyebrow,
  IconBadge,
  MiniFeature,
  Section,
} from "@/components/marketing/shared";
import { release, workflow } from "@/components/marketing/data";
import {
  ArrowRight,
  Boxes,
  ExternalLink,
  Server,
  TerminalSquare,
  Users,
} from "lucide-react";

const comparisons = [
  {
    name: "Crafty Controller",
    context:
      "A mature Minecraft-focused panel with multi-server administration, user management, schedules, and a broader control-panel feel.",
    why: [
      "More opinionated around creating Java Edition servers with Fabric, Quilt, NeoForge, Forge, or Vanilla.",
      "Modrinth search, compatibility checks, and modpack installs are part of the core server workflow.",
      "Smaller surface area when you want a simple dashboard for a personal server or small community.",
    ],
    wins: [
      "Better if you want a more traditional panel with mature multi-server admin workflows.",
      "Useful when you need more established user/role management and scheduled server tasks.",
    ],
  },
  {
    name: "Pterodactyl",
    context:
      "A powerful hosting panel built around nodes, wings, eggs, allocations, users, and multi-tenant game-server infrastructure.",
    why: [
      "Much less infrastructure to understand before the first Minecraft server is running.",
      "Minecraft-specific setup, Modrinth content, Java checks, files, backups, and player tools live in one focused UI.",
      "Better fit when you are self-hosting your own servers rather than operating a hosting platform.",
    ],
    wins: [
      "Better if you run many servers across nodes or need strong multi-tenant isolation.",
      "The right choice for hosting providers, mixed game fleets, advanced allocations, and larger admin teams.",
    ],
  },
  {
    name: "Docker + itzg/minecraft-server",
    context:
      "A great container image for running Minecraft servers declaratively with Compose, environment variables, and volumes.",
    why: [
      "Adds a browser UI for setup, Modrinth installs, player administration, console, logs, metrics, files, backups, and restore.",
      "Easier for people who do not want every change to be a Compose/env-var edit or terminal command.",
      "Still supports Docker deployment, but treats Docker as an install target rather than the whole management experience.",
    ],
    wins: [
      "Better if you prefer infrastructure-as-code and already manage servers through Compose, volumes, and automation.",
      "Excellent for headless, scriptable, minimal deployments where a web panel is unnecessary.",
    ],
  },
];

const ecosystemLinks = [
  [
    "Modrinth",
    "Mods and modpacks Fabricator can search and install from the dashboard.",
    "https://modrinth.com/",
  ],
  [
    "Fabric",
    "A popular lightweight Java Edition mod loader supported by Fabricator.",
    "https://fabricmc.net/",
  ],
  [
    "Quilt",
    "A community-focused mod loader option for compatible server setups.",
    "https://quiltmc.org/",
  ],
  [
    "NeoForge",
    "A modern Forge-family loader supported for Minecraft servers.",
    "https://neoforged.net/",
  ],
  [
    "Minecraft Forge",
    "The long-running Forge mod loader ecosystem for Java Edition servers.",
    "https://minecraftforge.net/",
  ],
  [
    "playit.gg",
    "Optional tunneling for sharing a self-hosted server without router port forwarding.",
    "https://playit.gg/",
  ],
] as const;

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "Fabricator | Self-Hosted Minecraft Server Manager" },
      {
        name: "description",
        content:
          "Create and manage Minecraft servers, mods, players, files, logs, metrics, and backups from one self-hosted dashboard.",
      },
    ],
  }),
  component: Home,
});

function Home() {
  return (
    <MarketingLayout active="home">
      <section className="mx-auto grid max-w-6xl gap-8 px-5 py-16 md:grid-cols-[1fr_1fr] md:items-center md:py-24">
        <div className="rounded-xl border border-white/10 bg-[#1b1b1b]/90 p-7 shadow-2xl shadow-black/50 backdrop-blur md:p-8">
          <Eyebrow>Open-source Minecraft server manager</Eyebrow>
          <h1 className="mt-4 max-w-2xl text-4xl font-bold leading-tight md:text-6xl">
            Manage Minecraft servers from one self-hosted web UI
          </h1>
          <p className="mt-6 max-w-xl text-base leading-8 text-zinc-400 md:text-lg">
            Fabricator helps you create Java Edition servers for Fabric, Quilt,
            NeoForge, Forge, or Vanilla, install Modrinth content, manage
            players, watch logs and metrics, edit files, and recover with
            backups.
          </p>
          <div className="mt-8 flex flex-wrap gap-3">
            <MarketingRouteLink
              href="/download"
              className="inline-flex h-12 items-center gap-2 rounded-full bg-orange-500 px-5 text-sm font-bold text-black shadow-lg shadow-orange-950/40 transition hover:bg-orange-400"
            >
              Download for Linux, Windows, or Docker
              <ArrowRight className="h-4 w-4" />
            </MarketingRouteLink>
            <MarketingRouteLink
              href="/#how"
              className="inline-flex h-12 items-center rounded-full bg-zinc-800 px-5 text-sm font-semibold text-white transition hover:bg-zinc-700"
            >
              See how it works
            </MarketingRouteLink>
          </div>
          <div className="mt-8 flex flex-wrap gap-x-3 gap-y-2 text-sm text-zinc-400">
            <MarketingRouteLink
              href="/docs"
              className="font-semibold text-zinc-200 underline decoration-orange-500/60 underline-offset-4"
            >
              Read the docs
            </MarketingRouteLink>
            <span>·</span>
            <a
              href="https://github.com/philderks/Fabricator"
              className="font-semibold text-zinc-200 underline decoration-orange-500/60 underline-offset-4"
            >
              View on GitHub
            </a>
          </div>
          <p className="mt-4 text-sm text-zinc-500">
            Self-hosted · Open source · Fabric + Forge + Quilt + Vanilla ·
            Player tools
          </p>
        </div>
        <div className="mx-auto w-full max-w-md overflow-hidden rounded-xl border border-white/10 bg-[#181818]/95 shadow-2xl shadow-black/60 backdrop-blur">
          <div className="flex items-center gap-2 border-b border-white/10 bg-black/25 px-5 py-4">
            <span className="h-3 w-3 rounded-full bg-red-500" />
            <span className="h-3 w-3 rounded-full bg-yellow-400" />
            <span className="h-3 w-3 rounded-full bg-green-500" />
            <span className="ml-3 font-mono text-xs text-zinc-500">
              fabricator
            </span>
          </div>
          <pre className="overflow-hidden whitespace-pre-wrap p-6 font-mono text-sm leading-7 text-zinc-300">
            <span className="text-orange-400">$</span> curl -fsSL{"\n"}
            {"  "}https://fabricator.site/install.sh | bash{"\n"}
            <span className="text-zinc-500">
              Installing Fabricator {release.version}...
            </span>
            {"\n"}
            <span className="text-green-400">✓</span> Done. Starting web UI on
            {"\n"}
            {"  "}http://localhost:5000{"\n"}
            <span className="text-orange-400">$</span> _
          </pre>
        </div>
      </section>

      <Section
        id="why"
        eyebrow="Why Fabricator"
        title="Minecraft-first server management, not just another panel"
      >
        <div className="grid gap-6 lg:grid-cols-[1.35fr_0.65fr]">
          <article className="rounded-xl border border-white/10 bg-[#1b1b1b]/90 p-6 shadow-2xl shadow-black/40 md:p-8">
            <p className="text-lg leading-8 text-zinc-400">
              Most server managers focus on generic hosting controls. Fabricator
              brings loader-aware setup, Modrinth content, player
              administration, files, logs, metrics, and backups into one focused
              dashboard.
            </p>
            <div className="mt-6 flex flex-wrap gap-3">
              <MarketingRouteLink
                href="/features"
                className="inline-flex items-center gap-2 rounded-md border border-white/10 bg-zinc-900 px-4 py-2 text-sm font-semibold text-white hover:bg-zinc-800"
              >
                View all features <ArrowRight className="h-4 w-4" />
              </MarketingRouteLink>
              <MarketingRouteLink
                href="/#shots"
                className="inline-flex items-center gap-2 rounded-md border border-white/10 px-4 py-2 text-sm font-semibold text-zinc-300 hover:text-white"
              >
                See the dashboard
              </MarketingRouteLink>
            </div>
          </article>
          <article className="rounded-xl border border-white/10 bg-[#1b1b1b]/90 p-6 shadow-2xl shadow-black/40">
            <IconBadge icon={Boxes} />
            <h3 className="mt-5 text-2xl font-semibold">
              Run the everyday Minecraft workflow from the dashboard
            </h3>
            <p className="mt-3 text-sm leading-7 text-zinc-400">
              Create Fabric, Quilt, NeoForge, Forge, or Vanilla servers, then
              handle compatible Modrinth installs, players, files, and recovery
              without bouncing between tools.
            </p>
          </article>
        </div>
        <div className="mt-5 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <MiniFeature
            icon={Server}
            title="Server setup & install"
            text="Create Fabric, Quilt, NeoForge, Forge, or Vanilla servers with version-aware setup."
          />
          <MiniFeature
            icon={Boxes}
            title="Modrinth content"
            text="Search, check compatibility, and install mods or modpacks from the dashboard."
          />
          <MiniFeature
            icon={TerminalSquare}
            title="Console and metrics"
            text="Start, stop, restart, send commands, and keep logs and status nearby."
          />
          <MiniFeature
            icon={Users}
            title="Player administration"
            text="Manage known players, whitelist, operators, bans, and kicks."
          />
        </div>
      </Section>

      <Section
        eyebrow="Comparison"
        title="Fabricator compared with the tools people actually use"
      >
        <p className="max-w-3xl text-lg leading-8 text-zinc-400">
          Fabricator is not trying to become a full hosting business panel or
          replace a clean Docker-only workflow. It is a Minecraft-first
          dashboard for server owners who want setup, mods, players, files,
          logs, metrics, and recovery in one focused place.
        </p>
        <div className="mt-8 grid gap-4">
          {comparisons.map((comparison) => (
            <article
              key={comparison.name}
              className="overflow-hidden rounded-xl border border-white/10 bg-white/[0.04] shadow-xl shadow-black/30"
            >
              <div className="border-b border-white/10 bg-white/[0.03] p-5 md:p-6">
                <p className="text-xs font-bold uppercase text-orange-400">
                  Compared with
                </p>
                <h3 className="mt-3 text-2xl font-semibold md:text-3xl">
                  {comparison.name}
                </h3>
                <p className="mt-3 max-w-4xl text-sm leading-7 text-zinc-400">
                  {comparison.context}
                </p>
              </div>
              <div className="grid md:grid-cols-2">
                <div className="p-5 md:p-6">
                  <h4 className="text-sm font-semibold text-white">
                    Why choose Fabricator
                  </h4>
                  <ul className="mt-3 list-disc space-y-2 pl-5 text-sm leading-7 text-zinc-400 marker:text-orange-400">
                    {comparison.why.map((item) => (
                      <li key={item}>{item}</li>
                    ))}
                  </ul>
                </div>
                <div className="border-t border-white/10 p-5 md:border-l md:border-t-0 md:p-6">
                  <h4 className="text-sm font-semibold text-white">
                    When {comparison.name.split(" ")[0]} wins
                  </h4>
                  <ul className="mt-3 list-disc space-y-2 pl-5 text-sm leading-7 text-zinc-400 marker:text-zinc-500">
                    {comparison.wins.map((item) => (
                      <li key={item}>{item}</li>
                    ))}
                  </ul>
                </div>
              </div>
            </article>
          ))}
        </div>
        <p className="mt-6 max-w-4xl text-sm leading-7 text-zinc-400">
          Short version: Crafty is the closest panel-style alternative,
          Pterodactyl is for serious hosting infrastructure, and
          itzg/minecraft-server is ideal for Docker-native operators. Fabricator
          sits between them: simpler than a hosting panel, more guided than a
          raw container.
        </p>
      </Section>

      <Section>
        <div className="rounded-xl border border-white/10 bg-[radial-gradient(circle_at_0%_0%,rgba(34,211,238,0.08),transparent_36%),rgba(255,255,255,0.04)] p-6 shadow-xl shadow-black/30 md:p-8">
          <Eyebrow>Minecraft ecosystem</Eyebrow>
          <h2 className="mt-3 max-w-4xl text-3xl font-bold leading-tight md:text-5xl">
            Built to fit the tools server owners already use
          </h2>
          <p className="mt-5 max-w-3xl text-lg leading-8 text-zinc-400">
            Fabricator works alongside trusted projects such as Modrinth,
            supports common mod loaders, and can use playit.gg when exposing a
            home server is awkward.
          </p>
          <div className="mt-8 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {ecosystemLinks.map(([name, text, href]) => (
              <a
                key={name}
                href={href}
                className="rounded-xl border border-white/10 bg-[#1b1b1b]/80 p-4 transition hover:-translate-y-0.5 hover:border-orange-500/50 hover:bg-[#202020]"
              >
                <span className="font-semibold text-white">{name}</span>
                <p className="mt-2 text-sm leading-6 text-zinc-400">{text}</p>
              </a>
            ))}
          </div>
        </div>
      </Section>

      <Section eyebrow="Download" title="Ready to install Fabricator?">
        <div className="rounded-xl border border-white/10 bg-[radial-gradient(circle_at_10%_10%,rgba(234,88,12,0.14),transparent_40%),#1b1b1b] p-6 shadow-2xl shadow-black/40 md:p-8">
          <p className="max-w-3xl text-lg leading-8 text-zinc-300">
            The detailed Linux installer, Windows download, Docker command,
            release links, requirements, and troubleshooting notes live on a
            focused download page.
          </p>
          <div className="mt-6 flex flex-wrap gap-3">
            <Link
              to="/download"
              className="inline-flex h-11 items-center gap-2 rounded-md bg-orange-500 px-4 text-sm font-bold text-black hover:bg-orange-400"
            >
              Open download page <ArrowRight className="h-4 w-4" />
            </Link>
            <a
              href="https://github.com/philderks/Fabricator/releases/latest"
              className="inline-flex h-11 items-center gap-2 rounded-md border border-white/10 bg-white/5 px-4 text-sm font-semibold text-white hover:bg-white/10"
            >
              Latest GitHub release <ExternalLink className="h-4 w-4" />
            </a>
          </div>
        </div>
      </Section>

      <Section
        id="how"
        eyebrow="How it works"
        title="A straightforward path from install to first launch"
      >
        <div className="grid gap-4 md:grid-cols-4">
          {workflow.map(([title, text], index) => (
            <article
              key={title}
              className="rounded-xl border border-white/10 bg-[#1b1b1b]/90 p-5 shadow-xl shadow-black/30"
            >
              <span className="flex h-11 w-11 items-center justify-center rounded-xl border border-white/10 bg-orange-500/15 text-sm font-black text-orange-300">
                {index + 1}
              </span>
              <h3 className="mt-5 text-xl font-semibold">{title}</h3>
              <p className="mt-3 text-sm leading-7 text-zinc-400">{text}</p>
            </article>
          ))}
        </div>
      </Section>

      <ScreenshotCarousel />
      <FAQSection />

      <Section
        eyebrow="Ready to manage your Minecraft server?"
        title="Get Fabricator running and start from the web UI"
      >
        <div className="rounded-xl border border-white/10 bg-[radial-gradient(circle_at_10%_10%,rgba(234,88,12,0.14),transparent_40%),#1b1b1b] p-6 shadow-2xl shadow-black/40 md:p-8">
          <p className="max-w-3xl text-lg leading-8 text-zinc-300">
            Fabricator is free, self-hosted, and open source. Use the Linux
            installer, grab the Windows executable, or run the Docker image with
            persistent data in a volume.
          </p>
          <div className="mt-6 flex flex-wrap gap-3">
            <Link
              to="/download"
              className="inline-flex h-11 items-center gap-2 rounded-md bg-orange-500 px-4 text-sm font-bold text-black hover:bg-orange-400"
            >
              See downloads <ArrowRight className="h-4 w-4" />
            </Link>
            <a
              href="https://github.com/philderks/Fabricator/releases/latest"
              className="inline-flex h-11 items-center gap-2 rounded-md border border-white/10 bg-white/5 px-4 text-sm font-semibold text-white hover:bg-white/10"
            >
              Latest GitHub release <ExternalLink className="h-4 w-4" />
            </a>
          </div>
        </div>
      </Section>
    </MarketingLayout>
  );
}
