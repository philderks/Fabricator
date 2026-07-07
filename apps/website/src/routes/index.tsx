import { createFileRoute, Link } from '@tanstack/react-router';
import { HomeLayout } from 'fumadocs-ui/layouts/home';
import { baseOptions } from '@/lib/layout.shared';
import {
  ArrowRight,
  Boxes,
  ExternalLink,
  HardDrive,
  RotateCcw,
  Server,
  ShieldCheck,
  TerminalSquare,
  Users,
} from 'lucide-react';

export const Route = createFileRoute('/')({
  component: Home,
});

function Home() {
  return (
    <HomeLayout {...baseOptions()}>
      <div className="min-h-[calc(100dvh-3.5rem)]">
        <section className="mx-auto grid w-full max-w-6xl gap-10 px-6 pb-16 pt-16 md:grid-cols-[1.05fr_0.95fr] md:items-center md:pt-24">
          <div>
            <div className="mb-5 inline-flex items-center gap-2 rounded-full border border-fd-border bg-fd-card px-3 py-1 text-sm text-fd-muted-foreground">
              <Server className="h-4 w-4 text-fd-primary" />
              Linux-first Minecraft server management
            </div>
            <h1 className="max-w-3xl text-4xl font-semibold leading-tight tracking-normal text-fd-foreground md:text-6xl">
              Fabricator
            </h1>
            <p className="mt-5 max-w-2xl text-base leading-7 text-fd-muted-foreground md:text-lg">
              Create, run, back up, update, and inspect Minecraft servers from a self-hosted web dashboard with a Python backend, Vue control panel, and a small system CLI.
            </p>
            <div className="mt-8 flex flex-wrap gap-3">
              <Link
                to="/docs/$"
                params={{ _splat: 'getting-started/installation' }}
                className="inline-flex h-11 items-center gap-2 rounded-md bg-fd-primary px-4 text-sm font-medium text-fd-primary-foreground transition hover:opacity-90"
              >
                Install Fabricator
                <ArrowRight className="h-4 w-4" />
              </Link>
              <a
                href="https://github.com/philderks/Fabricator"
                className="inline-flex h-11 items-center gap-2 rounded-md border border-fd-border bg-fd-card px-4 text-sm font-medium text-fd-foreground transition hover:bg-fd-accent"
              >
                <ExternalLink className="h-4 w-4" />
                GitHub
              </a>
            </div>
          </div>

          <div className="grid gap-3 rounded-lg border border-fd-border bg-fd-card p-3 shadow-2xl shadow-black/20">
            <Feature icon={TerminalSquare} title="Live console" text="Start, stop, restart, inspect logs, and send commands from the browser." />
            <Feature icon={Boxes} title="Mods and modpacks" text="Search Modrinth and install compatible Fabric, Forge, NeoForge, Quilt, and Vanilla files." />
            <Feature icon={RotateCcw} title="Backups" text="Schedule snapshots, download archives, and restore worlds when you need to roll back." />
            <Feature icon={Users} title="Players" text="Manage whitelist, operators, bans, IP bans, and runtime player state." />
            <Feature icon={HardDrive} title="Files" text="Browse and edit server files inside each server install directory." />
            <Feature icon={ShieldCheck} title="Operations" text="Configure authentication, reverse proxies, playit.gg tunnels, and updates." />
          </div>
        </section>

        <section className="border-t border-fd-border bg-fd-muted/40">
          <div className="mx-auto grid max-w-6xl gap-4 px-6 py-8 md:grid-cols-3">
            <QuickLink title="Getting Started" text="Requirements, installation, Docker, authentication, and reverse proxy setup." splat="getting-started/introduction" />
            <QuickLink title="Guides" text="Dashboard, console, players, mods, files, backups, tunnels, settings, and updates." splat="guides/dashboard-overview" />
            <QuickLink title="Reference" text="CLI commands, HTTP API shape, Java management, and multi-server configuration." splat="reference/cli" />
          </div>
        </section>
      </div>
    </HomeLayout>
  );
}

function Feature({
  icon: Icon,
  title,
  text,
}: {
  icon: typeof Server;
  title: string;
  text: string;
}) {
  return (
    <div className="grid grid-cols-[2.25rem_1fr] gap-3 rounded-md border border-fd-border bg-fd-background/55 p-3">
      <div className="flex h-9 w-9 items-center justify-center rounded-md bg-fd-primary/10 text-fd-primary">
        <Icon className="h-4 w-4" />
      </div>
      <div>
        <h2 className="text-sm font-medium text-fd-foreground">{title}</h2>
        <p className="mt-1 text-sm leading-6 text-fd-muted-foreground">{text}</p>
      </div>
    </div>
  );
}

function QuickLink({ title, text, splat }: { title: string; text: string; splat: string }) {
  return (
    <Link
      to="/docs/$"
      params={{ _splat: splat }}
      className="rounded-md border border-fd-border bg-fd-background p-4 transition hover:bg-fd-accent"
    >
      <div className="flex items-center justify-between gap-3">
        <h2 className="text-base font-medium text-fd-foreground">{title}</h2>
        <ArrowRight className="h-4 w-4 shrink-0 text-fd-primary" />
      </div>
      <p className="mt-2 text-sm leading-6 text-fd-muted-foreground">{text}</p>
    </Link>
  );
}
