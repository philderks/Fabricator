import { Link, useRouter } from '@tanstack/react-router';
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from '@/components/ui/accordion';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import {
  Carousel,
  type CarouselApi,
  CarouselContent,
  CarouselItem,
  CarouselNext,
  CarouselPrevious,
} from '@/components/ui/carousel';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import type { LucideIcon } from 'lucide-react';
import {
  ArrowRight,
  Boxes,
  Check,
  Copy,
  Download,
  ExternalLink,
  HardDrive,
  Monitor,
  Pause,
  Play,
  RotateCcw,
  Server,
  TerminalSquare,
  Users,
} from 'lucide-react';
import { type MouseEvent, useCallback, useEffect, useState, type ReactNode } from 'react';

type ActivePage = 'home' | 'features' | 'download' | 'privacy' | 'impressum';
type MarketingHomeSection = 'how' | 'shots' | 'faq' | null;
type MarketingLink = readonly [label: string, href: string];
type MarketingFeatureItem = readonly [title: string, text: string];
type MarketingFeatureGroup = {
  value: string;
  eyebrow: string;
  icon: LucideIcon;
  title: string;
  text: string;
  items: MarketingFeatureItem[];
};
type MarketingScreenshot = {
  title: string;
  text: string;
  image: string;
  alt: string;
};
type MarketingFaqItem = readonly [question: string, answer: string];
type MarketingPlatform = {
  value: 'linux' | 'windows' | 'docker';
  name: string;
  icon: LucideIcon;
  eyebrow: string;
  title: string;
  status: string;
  command?: string;
  text: string;
  primaryAction?: MarketingLink;
  meta: MarketingFeatureItem[];
  links: MarketingLink[];
  note?: string;
};

const release = {
  version: 'v0.9.2',
  date: 'Jul 3, 2026',
};

const navItems = [
  { label: 'Features', href: '/features', active: 'features' },
  { label: 'Download', href: '/download', active: 'download', cta: true },
  { label: 'How it works', href: '/#how', active: 'home' },
  { label: 'Inside the app', href: '/#shots', active: 'home' },
  { label: 'FAQ', href: '/#faq', active: 'home' },
  { label: 'Docs', href: '/docs', active: 'docs' },
];

const featureGroups: MarketingFeatureGroup[] = [
  {
    value: 'modrinth',
    eyebrow: 'Modrinth',
    icon: Boxes,
    title: 'Modrinth mods & modpacks',
    text: 'Search Modrinth, review compatible versions, and install mods or modpacks without leaving the dashboard.',
    items: [
      ['Integrated Modrinth search', 'Find compatible mods and modpacks from the same UI you use to manage the server.'],
    ],
  },
  {
    value: 'setup',
    eyebrow: 'Setup',
    icon: Server,
    title: 'Server setup & install',
    text: 'Create Fabric, Quilt, NeoForge, Forge, or Vanilla servers, choose Minecraft and loader versions, and let Fabricator prepare the install path while checking requirements.',
    items: [
      ['Java compatibility help', 'Surface guidance when the host is missing a matching runtime.'],
      ['Version-aware creation', 'Pick Minecraft, loader, and loader versions during setup.'],
      ['Linux, Windows, and Docker installs', 'Install with a script, executable, or GHCR image.'],
    ],
  },
  {
    value: 'operations',
    eyebrow: 'Operations',
    icon: TerminalSquare,
    title: 'Console, logs & live metrics',
    text: 'Start, stop, restart, send commands, and keep logs, player counts, versions, CPU, and RAM close by.',
    items: [
      ['Player administration', 'Manage whitelist, operators, bans, IP bans, kicks, and runtime player state.'],
      ['Files & settings', 'Browse server files, edit text configs, and update common settings.'],
      ['playit.gg tunnels', 'Expose servers without router port forwarding.'],
      ['Server health overview', 'See status, versions, players, CPU, RAM, modpacks, and mods at a glance.'],
    ],
  },
  {
    value: 'safety',
    eyebrow: 'Safety',
    icon: RotateCcw,
    title: 'Backups & restore',
    text: 'Create zip backups before risky changes and restore a server safely while it is offline.',
    items: [
      ['Restore-safe workflow', 'Rollback operations are easier to reason about when the server is stopped.'],
      ['Self-hosted and open source', 'Run Fabricator on your own machine and inspect the source.'],
    ],
  },
];

const platforms: MarketingPlatform[] = [
  {
    value: 'linux',
    name: 'Linux',
    icon: TerminalSquare,
    eyebrow: 'Recommended',
    title: 'Install with one command',
    status: 'Available now',
    command: 'curl -fsSL https://fabricator.site/install.sh | bash',
    text: 'Install Fabricator on the Linux machine that will host or manage your Minecraft servers.',
    meta: [
      ['Version', release.version],
      ['Published', release.date],
    ],
    links: [
      ['Download install.sh', 'https://fabricator.site/install.sh'],
      ['View script source', 'https://github.com/philderks/Fabricator/blob/main/tools/install.sh'],
      ['Read the docs', '/docs'],
    ],
  },
  {
    value: 'windows',
    name: 'Windows',
    icon: Monitor,
    eyebrow: 'Desktop app',
    title: 'Download .exe for Windows',
    status: 'Available now',
    text: 'Download the latest Windows executable and launch Fabricator directly on your Windows machine.',
    primaryAction: ['Download .exe for Windows', 'https://github.com/philderks/Fabricator/releases/download/v0.9.2/Fabricator-v0.9.2.exe'],
    meta: [
      ['Version', release.version],
      ['Published', release.date],
      ['File', 'Fabricator-v0.9.2.exe'],
      ['Size', '19.6 MB'],
    ],
    links: [
      ['View latest release', 'https://github.com/philderks/Fabricator/releases/tag/v0.9.2'],
      ['Read the docs', '/docs'],
    ],
    note: 'SHA256: 944a008c3edf5e0beb4701aa0f524c1d1141f2f47b6d1dafe54b86c929c89957',
  },
  {
    value: 'docker',
    name: 'Docker',
    icon: HardDrive,
    eyebrow: 'Container image',
    title: 'Run with Docker',
    status: 'Available now',
    command: 'docker run -d --name fabricator -p 127.0.0.1:5000:5000 -v fabricator-data:/data --restart unless-stopped ghcr.io/philderks/fabricator:latest',
    text: 'Run Fabricator from the published GHCR image with persistent data stored in a Docker volume.',
    meta: [
      ['Version', release.version],
      ['Published', release.date],
    ],
    links: [
      ['View docker-compose.yml', 'https://github.com/philderks/Fabricator/blob/main/docker-compose.yml'],
      ['View container package', 'https://github.com/philderks/Fabricator/pkgs/container/fabricator'],
      ['Read the docs', '/docs/getting-started/docker'],
    ],
    note: 'Binds the dashboard to 127.0.0.1:5000 by default. Put a reverse proxy, firewall, or VPN in front before exposing it publicly.',
  },
];

const workflow = [
  ['Install Fabricator', 'Run the Linux installer, Windows executable, or Docker image on the machine you want to host or manage, then open the web UI.'],
  ['Create your Minecraft server', 'Choose a name, Minecraft version, loader, port, and install path. Fabricator checks Java requirements before setup.'],
  ['Add mods or a modpack from Modrinth', 'Install content from Modrinth, then adjust files and settings from the dashboard.'],
  ['Run, monitor, and back it up', 'Start or restart the server, watch logs and metrics, manage players, browse files, and create backups before risky changes.'],
];

const screenshotCards: MarketingScreenshot[] = [
  {
    title: 'Server overview',
    text: 'Track player counts, uptime, version details, performance, installed mods, recent logs, and common actions.',
    image: '/fabricator-screenshots/overview.webp',
    alt: 'Fabricator overview dashboard for a demo Fabric server with status cards, performance metrics, recent logs, installed mods, and quick actions.',
  },
  {
    title: 'Live console',
    text: 'Watch logs, filter levels, download output, refresh the stream, and send commands from the browser.',
    image: '/fabricator-screenshots/console.webp',
    alt: 'Fabricator console page showing Minecraft server startup and save logs with log-level filters and a command input.',
  },
  {
    title: 'Player management',
    text: 'Review online players, known players, operators, whitelist entries, and bans in one place.',
    image: '/fabricator-screenshots/players.webp',
    alt: 'Fabricator players page showing tabs for all players, whitelist, operators, and banned players with empty player lists.',
  },
  {
    title: 'Installed mods',
    text: 'See installed mods, select them in bulk, and remove local mod files without leaving the panel.',
    image: '/fabricator-screenshots/mods.webp',
    alt: 'Fabricator mods page listing installed mods with remove actions.',
  },
  {
    title: 'Browse Modrinth',
    text: 'Search compatible Modrinth mods and install the right result directly into the selected server.',
    image: '/fabricator-screenshots/browse-mods.webp',
    alt: 'Fabricator browse mods modal searching for a Modrinth result with an install button.',
  },
  {
    title: 'File browser',
    text: 'Browse the server directory, inspect common folders, and jump into configuration files from the web UI.',
    image: '/fabricator-screenshots/files.webp',
    alt: 'Fabricator files page showing a Minecraft server directory with folders like mods, logs, libraries, versions, and world.',
  },
  {
    title: 'Backups',
    text: 'Check backup schedules, snapshot totals, last restore points, and create quick backups before risky changes.',
    image: '/fabricator-screenshots/backups.webp',
    alt: 'Fabricator backups page with snapshot statistics, scheduled backup time, filters, and a quick backup button.',
  },
  {
    title: 'playit.gg tunnels',
    text: 'Enable a shared playit.gg tunnel agent so friends can reach a server without router setup.',
    image: '/fabricator-screenshots/playit.webp',
    alt: 'Fabricator playit.gg page explaining the tunnel agent and showing an enable playit.gg button.',
  },
  {
    title: 'Server properties',
    text: 'Edit common server.properties safely in basic mode, with expert mode available for deeper configuration.',
    image: '/fabricator-screenshots/properties.webp',
    alt: 'Fabricator properties page showing editable server name, message of the day, port, max players, difficulty, and gamemode fields.',
  },
  {
    title: 'Java runtimes',
    text: 'Review detected Java runtimes and install additional Java versions for Minecraft compatibility.',
    image: '/fabricator-screenshots/settings.webp',
    alt: 'Fabricator settings page showing Java runtime management and about information.',
  },
];

const faqItems: MarketingFaqItem[] = [
  ['Is Fabricator free and open source?', 'Yes. Fabricator is free to use, self-hosted, and open source, with the source code available on GitHub.'],
  ['What modloaders does Fabricator support?', 'Fabricator supports Fabric, Quilt, NeoForge, Forge, and Vanilla Java Edition server workflows.'],
  ['Does Fabricator support Bedrock servers?', 'Fabricator is focused on Java Edition servers. Bedrock support is not part of the current scope.'],
  ['Can Fabricator install mods and modpacks from Modrinth?', 'Yes. Modrinth search, compatibility checks, and install actions are part of the core workflow.'],
  ['How does it compare with Crafty, Pterodactyl, or Docker?', 'Fabricator is simpler than hosting panels and more guided than raw container workflows. It is meant for personal servers and small communities.'],
  ['Can Fabricator manage players?', 'Yes. You can review known and online players, operators, whitelist entries, bans, IP bans, and kicks.'],
  ['How do I install Fabricator?', 'Use the Linux installer, Windows executable, or Docker image from the download page.'],
];

export function MarketingLayout({
  active,
  legal = false,
  children,
}: {
  active: ActivePage;
  legal?: boolean;
  children: ReactNode;
}) {
  const activeSection = useActiveMarketingSection(active);

  return (
    <div className="min-h-screen bg-[#0b0b0b] text-white">
      <div className="fixed inset-0 -z-10 bg-[radial-gradient(circle_at_10%_20%,rgba(34,211,238,0.08),transparent_25%),radial-gradient(circle_at_80%_0%,rgba(234,88,12,0.12),transparent_24%),linear-gradient(180deg,#080808_0%,#141414_100%)]" />
      <header className="sticky top-0 z-40 border-b border-white/10 bg-[#0f0f0f]/85 backdrop-blur-xl">
        <nav className="mx-auto flex h-20 max-w-6xl items-center justify-between px-5">
          <MarketingRouteLink href="/" className="flex items-center gap-3 font-semibold text-white" ariaLabel="Fabricator home">
            <FabricatorMark />
            <span>Fabricator</span>
          </MarketingRouteLink>
          <div className="hidden items-center gap-2 md:flex">
            {navItems.map((item) => (
              <NavLink key={item.label} item={item} active={active} activeSection={activeSection} />
            ))}
          </div>
          <MarketingRouteLink href="/download" className="inline-flex h-10 items-center rounded-md bg-orange-500 px-4 text-sm font-semibold text-black shadow-lg shadow-orange-950/30 md:hidden">
            Download
          </MarketingRouteLink>
        </nav>
      </header>

      <main>{children}</main>

      <footer className={legal ? 'border-t border-white/10 bg-[#0b0b0b]' : 'border-t border-white/10 bg-[#080808]'}>
        <div className="mx-auto flex max-w-6xl flex-col gap-4 px-5 py-8 text-sm text-zinc-500 md:flex-row md:items-center md:justify-between">
          <p>© 2026 Fabricator</p>
          <div className="flex gap-5">
            <Link to="/privacy" className="hover:text-orange-300">Privacy Policy</Link>
            <Link to="/impressum" className="hover:text-orange-300">Legal Notice</Link>
          </div>
        </div>
      </footer>
    </div>
  );
}

function useActiveMarketingSection(active: ActivePage): MarketingHomeSection {
  const [activeSection, setActiveSection] = useState<MarketingHomeSection>(() => getHashSection());

  useEffect(() => {
    if (active !== 'home') {
      setActiveSection(null);
      return;
    }

    const updateActiveSection = () => {
      const sectionIds = ['how', 'shots', 'faq'] as const;
      const current = sectionIds.reduce<MarketingHomeSection>((visibleSection, sectionId) => {
        const section = document.getElementById(sectionId);
        if (!section) return visibleSection;

        const sectionTop = section.getBoundingClientRect().top;
        return sectionTop <= 180 ? sectionId : visibleSection;
      }, null);

      setActiveSection(current ?? getHashSection());
    };

    updateActiveSection();
    window.addEventListener('scroll', updateActiveSection, { passive: true });
    window.addEventListener('hashchange', updateActiveSection);
    window.addEventListener('resize', updateActiveSection);

    return () => {
      window.removeEventListener('scroll', updateActiveSection);
      window.removeEventListener('hashchange', updateActiveSection);
      window.removeEventListener('resize', updateActiveSection);
    };
  }, [active]);

  return activeSection;
}

function getHashSection(): MarketingHomeSection {
  if (typeof window === 'undefined') return null;

  const hash = window.location.hash.slice(1);
  return hash === 'how' || hash === 'shots' || hash === 'faq' ? hash : null;
}

function NavLink({
  item,
  active,
  activeSection,
}: {
  item: (typeof navItems)[number];
  active: ActivePage;
  activeSection: MarketingHomeSection;
}) {
  const router = useRouter();
  const hashSection = item.href.startsWith('/#') ? item.href.slice(2) : null;
  const isActive = hashSection
    ? active === 'home' && activeSection === hashSection
    : item.active === active;
  const activeUnderline = isActive
    ? 'after:absolute after:left-3 after:right-3 after:-bottom-2 after:h-0.5 after:rounded-full after:bg-primary after:shadow-[0_0_12px_rgba(249,115,22,0.55)]'
    : 'after:absolute after:left-3 after:right-3 after:-bottom-2 after:h-0.5 after:rounded-full after:bg-primary after:opacity-0 after:transition-opacity hover:after:opacity-35';
  const className = item.cta
    ? `relative rounded-md border px-4 py-2 text-sm font-semibold transition ${activeUnderline} ${active === 'download' ? 'border-orange-400 bg-orange-500 text-black' : 'border-orange-500/40 bg-orange-500/15 text-orange-100 hover:bg-orange-500/25'}`
    : `relative rounded-md px-3 py-2 text-sm font-medium transition ${activeUnderline} ${isActive ? 'text-white' : 'text-zinc-400 hover:text-white'}`;

  const handleClick = (event: MouseEvent<HTMLAnchorElement>) => {
    handleMarketingNavigation(event, router, item.href);
  };

  return <a href={item.href} className={className} onClick={handleClick}>{item.label}</a>;
}

function MarketingRouteLink({
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
  href: string,
) {
  if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.altKey || event.ctrlKey || event.shiftKey) {
    return;
  }

  if (!href.startsWith('/')) {
    return;
  }

  event.preventDefault();
  void navigateMarketing(router, href);
}

async function navigateMarketing(router: MarketingRouter, href: string) {
  if (typeof window === 'undefined') return;

  const hashIndex = href.indexOf('#');
  const pathname = hashIndex >= 0 ? href.slice(0, hashIndex) || '/' : href;
  const hash = hashIndex >= 0 ? href.slice(hashIndex + 1) : '';
  const currentPathname = window.location.pathname;

  if (hash && currentPathname === pathname) {
    window.history.pushState(null, '', href);
    scrollToMarketingHash(hash, 'smooth');
    return;
  }

  await withMarketingViewTransition(async () => {
    await router.navigate({ to: pathname });
  });

  if (hash) {
    window.history.replaceState(null, '', href);
    scrollToMarketingHash(hash, 'auto');
  } else {
    window.scrollTo({ top: 0, behavior: 'auto' });
  }
}

async function withMarketingViewTransition(callback: () => Promise<void>) {
  if (typeof document === 'undefined' || typeof window === 'undefined') {
    await callback();
    return;
  }

  const documentWithTransitions = document as Document & {
    startViewTransition?: (callback: () => Promise<void>) => { finished: Promise<void> };
  };

  if (
    !documentWithTransitions.startViewTransition ||
    window.matchMedia('(prefers-reduced-motion: reduce)').matches
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

    target.scrollIntoView({ behavior, block: 'start' });
  });
}

export function HeroSection() {
  return (
    <section className="mx-auto grid max-w-6xl gap-8 px-5 py-16 md:grid-cols-[1fr_1fr] md:items-center md:py-24">
      <div className="rounded-xl border border-white/10 bg-[#1b1b1b]/90 p-7 shadow-2xl shadow-black/50 backdrop-blur md:p-8">
        <Eyebrow>Open-source Minecraft server manager</Eyebrow>
        <h1 className="mt-4 max-w-2xl text-4xl font-bold leading-tight md:text-6xl">
          Manage Minecraft servers from one self-hosted web UI
        </h1>
        <p className="mt-6 max-w-xl text-base leading-8 text-zinc-400 md:text-lg">
          Fabricator helps you create Java Edition servers for Fabric, Quilt, NeoForge, Forge, or Vanilla, install Modrinth content, manage players, watch logs and metrics, edit files, and recover with backups.
        </p>
        <div className="mt-8 flex flex-wrap gap-3">
          <MarketingRouteLink href="/download" className="inline-flex h-12 items-center gap-2 rounded-full bg-orange-500 px-5 text-sm font-bold text-black shadow-lg shadow-orange-950/40 transition hover:bg-orange-400">
            Download for Linux, Windows, or Docker
            <ArrowRight className="h-4 w-4" />
          </MarketingRouteLink>
          <MarketingRouteLink href="/#how" className="inline-flex h-12 items-center rounded-full bg-zinc-800 px-5 text-sm font-semibold text-white transition hover:bg-zinc-700">
            See how it works
          </MarketingRouteLink>
        </div>
        <div className="mt-8 flex flex-wrap gap-x-3 gap-y-2 text-sm text-zinc-400">
          <MarketingRouteLink href="/docs" className="font-semibold text-zinc-200 underline decoration-orange-500/60 underline-offset-4">Read the docs</MarketingRouteLink>
          <span>·</span>
          <a href="https://github.com/philderks/Fabricator" className="font-semibold text-zinc-200 underline decoration-orange-500/60 underline-offset-4">View on GitHub</a>
        </div>
        <p className="mt-4 text-sm text-zinc-500">Self-hosted · Open source · Fabric + Forge + Quilt + Vanilla · Player tools</p>
      </div>
      <TerminalPanel />
    </section>
  );
}

function TerminalPanel() {
  return (
    <div className="mx-auto w-full max-w-md overflow-hidden rounded-xl border border-white/10 bg-[#181818]/95 shadow-2xl shadow-black/60 backdrop-blur">
      <div className="flex items-center gap-2 border-b border-white/10 bg-black/25 px-5 py-4">
        <span className="h-3 w-3 rounded-full bg-red-500" />
        <span className="h-3 w-3 rounded-full bg-yellow-400" />
        <span className="h-3 w-3 rounded-full bg-green-500" />
        <span className="ml-3 font-mono text-xs text-zinc-500">fabricator</span>
      </div>
      <pre className="overflow-hidden whitespace-pre-wrap p-6 font-mono text-sm leading-7 text-zinc-300">
        <span className="text-orange-400">$</span> curl -fsSL{'\n'}
        {'  '}https://fabricator.site/install.sh | bash{'\n'}
        <span className="text-zinc-500">Installing Fabricator {release.version}...</span>{'\n'}
        <span className="text-green-400">✓</span> Done. Starting web UI on{'\n'}
        {'  '}http://localhost:5000{'\n'}
        <span className="text-orange-400">$</span> _
      </pre>
    </div>
  );
}

export function WhySection() {
  return (
    <Section id="why" eyebrow="Why Fabricator" title="Minecraft-first server management, not just another panel">
      <div className="grid gap-6 lg:grid-cols-[1.35fr_0.65fr]">
        <article className="rounded-xl border border-white/10 bg-[#1b1b1b]/90 p-6 shadow-2xl shadow-black/40 md:p-8">
          <p className="text-lg leading-8 text-zinc-400">
            Most server managers focus on generic hosting controls. Fabricator brings loader-aware setup, Modrinth content, player administration, files, logs, metrics, and backups into one focused dashboard.
          </p>
          <div className="mt-6 flex flex-wrap gap-3">
            <MarketingRouteLink href="/features" className="inline-flex items-center gap-2 rounded-md border border-white/10 bg-zinc-900 px-4 py-2 text-sm font-semibold text-white hover:bg-zinc-800">
              View all features <ArrowRight className="h-4 w-4" />
            </MarketingRouteLink>
            <MarketingRouteLink href="/#shots" className="inline-flex items-center gap-2 rounded-md border border-white/10 px-4 py-2 text-sm font-semibold text-zinc-300 hover:text-white">
              See the dashboard
            </MarketingRouteLink>
          </div>
        </article>
        <article className="rounded-xl border border-white/10 bg-[#1b1b1b]/90 p-6 shadow-2xl shadow-black/40">
          <IconBadge icon={Boxes} />
          <h3 className="mt-5 text-2xl font-semibold">Run the everyday Minecraft workflow from the dashboard</h3>
          <p className="mt-3 text-sm leading-7 text-zinc-400">
            Create Fabric, Quilt, NeoForge, Forge, or Vanilla servers, then handle compatible Modrinth installs, players, files, and recovery without bouncing between tools.
          </p>
        </article>
      </div>
      <div className="mt-5 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <MiniFeature icon={Server} title="Server setup & install" text="Create Fabric, Quilt, NeoForge, Forge, or Vanilla servers with version-aware setup." />
          <MiniFeature icon={Boxes} title="Modrinth content" text="Search, check compatibility, and install mods or modpacks from the dashboard." />
          <MiniFeature icon={TerminalSquare} title="Console and metrics" text="Start, stop, restart, send commands, and keep logs and status nearby." />
          <MiniFeature icon={Users} title="Player administration" text="Manage known players, whitelist, operators, bans, IP bans, and kicks." />
      </div>
    </Section>
  );
}

export function ComparisonSection() {
  const comparisons = [
    {
      name: 'Crafty Controller',
      context: 'A mature Minecraft-focused panel with multi-server administration, user management, schedules, and a broader control-panel feel.',
      why: [
        'More opinionated around creating Java Edition servers with Fabric, Quilt, NeoForge, Forge, or Vanilla.',
        'Modrinth search, compatibility checks, and modpack installs are part of the core server workflow.',
        'Smaller surface area when you want a simple dashboard for a personal server or small community.',
      ],
      wins: [
        'Better if you want a more traditional panel with mature multi-server admin workflows.',
        'Useful when you need more established user/role management and scheduled server tasks.',
      ],
    },
    {
      name: 'Pterodactyl',
      context: 'A powerful hosting panel built around nodes, wings, eggs, allocations, users, and multi-tenant game-server infrastructure.',
      why: [
        'Much less infrastructure to understand before the first Minecraft server is running.',
        'Minecraft-specific setup, Modrinth content, Java checks, files, backups, and player tools live in one focused UI.',
        'Better fit when you are self-hosting your own servers rather than operating a hosting platform.',
      ],
      wins: [
        'Better if you run many servers across nodes or need strong multi-tenant isolation.',
        'The right choice for hosting providers, mixed game fleets, advanced allocations, and larger admin teams.',
      ],
    },
    {
      name: 'Docker + itzg/minecraft-server',
      context: 'A great container image for running Minecraft servers declaratively with Compose, environment variables, and volumes.',
      why: [
        'Adds a browser UI for setup, Modrinth installs, player administration, console, logs, metrics, files, backups, and restore.',
        'Easier for people who do not want every change to be a Compose/env-var edit or terminal command.',
        'Still supports Docker deployment, but treats Docker as an install target rather than the whole management experience.',
      ],
      wins: [
        'Better if you prefer infrastructure-as-code and already manage servers through Compose, volumes, and automation.',
        'Excellent for headless, scriptable, minimal deployments where a web panel is unnecessary.',
      ],
    },
  ];

  return (
    <Section eyebrow="Comparison" title="Fabricator compared with the tools people actually use">
      <p className="max-w-3xl text-lg leading-8 text-zinc-400">
        Fabricator is not trying to become a full hosting business panel or replace a clean Docker-only workflow. It is a Minecraft-first dashboard for server owners who want setup, mods, players, files, logs, metrics, and recovery in one focused place.
      </p>
      <div className="mt-8 grid gap-4">
        {comparisons.map((comparison) => (
          <article key={comparison.name} className="overflow-hidden rounded-xl border border-white/10 bg-white/[0.04] shadow-xl shadow-black/30">
            <div className="border-b border-white/10 bg-white/[0.03] p-5 md:p-6">
              <p className="text-xs font-bold uppercase text-orange-400">Compared with</p>
              <h3 className="mt-3 text-2xl font-semibold md:text-3xl">{comparison.name}</h3>
              <p className="mt-3 max-w-4xl text-sm leading-7 text-zinc-400">{comparison.context}</p>
            </div>
            <div className="grid md:grid-cols-2">
              <div className="p-5 md:p-6">
                <h4 className="text-sm font-semibold text-white">Why choose Fabricator</h4>
                <ul className="mt-3 list-disc space-y-2 pl-5 text-sm leading-7 text-zinc-400 marker:text-orange-400">
                  {comparison.why.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              </div>
              <div className="border-t border-white/10 p-5 md:border-l md:border-t-0 md:p-6">
                <h4 className="text-sm font-semibold text-white">When {comparison.name.split(' ')[0]} wins</h4>
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
        Short version: Crafty is the closest panel-style alternative, Pterodactyl is for serious hosting infrastructure, and itzg/minecraft-server is ideal for Docker-native operators. Fabricator sits between them: simpler than a hosting panel, more guided than a raw container.
      </p>
    </Section>
  );
}

export function EcosystemSection() {
  const links = [
    ['Modrinth', 'Mods and modpacks Fabricator can search and install from the dashboard.', 'https://modrinth.com/'],
    ['Fabric', 'A popular lightweight Java Edition mod loader supported by Fabricator.', 'https://fabricmc.net/'],
    ['Quilt', 'A community-focused mod loader option for compatible server setups.', 'https://quiltmc.org/'],
    ['NeoForge', 'A modern Forge-family loader supported for Minecraft servers.', 'https://neoforged.net/'],
    ['Minecraft Forge', 'The long-running Forge mod loader ecosystem for Java Edition servers.', 'https://minecraftforge.net/'],
    ['playit.gg', 'Optional tunneling for sharing a self-hosted server without router port forwarding.', 'https://playit.gg/'],
  ];

  return (
    <Section>
      <div className="rounded-xl border border-white/10 bg-[radial-gradient(circle_at_0%_0%,rgba(34,211,238,0.08),transparent_36%),rgba(255,255,255,0.04)] p-6 shadow-xl shadow-black/30 md:p-8">
        <Eyebrow>Minecraft ecosystem</Eyebrow>
        <h2 className="mt-3 max-w-4xl text-3xl font-bold leading-tight md:text-5xl">Built to fit the tools server owners already use</h2>
        <p className="mt-5 max-w-3xl text-lg leading-8 text-zinc-400">
          Fabricator works alongside trusted projects such as Modrinth, supports common mod loaders, and can use playit.gg when exposing a home server is awkward.
        </p>
        <div className="mt-8 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {links.map(([name, text, href]) => (
            <a key={name} href={href} className="rounded-xl border border-white/10 bg-[#1b1b1b]/80 p-4 transition hover:-translate-y-0.5 hover:border-orange-500/50 hover:bg-[#202020]">
              <span className="font-semibold text-white">{name}</span>
              <p className="mt-2 text-sm leading-6 text-zinc-400">{text}</p>
            </a>
          ))}
        </div>
      </div>
    </Section>
  );
}

export function ReadySection({ compact = false }: { compact?: boolean }) {
  return (
    <Section eyebrow={compact ? 'Download' : 'Ready to manage your Minecraft server?'} title={compact ? 'Ready to install Fabricator?' : 'Get Fabricator running and start from the web UI'}>
      <div className="rounded-xl border border-white/10 bg-[radial-gradient(circle_at_10%_10%,rgba(234,88,12,0.14),transparent_40%),#1b1b1b] p-6 shadow-2xl shadow-black/40 md:p-8">
        <p className="max-w-3xl text-lg leading-8 text-zinc-300">
          {compact
            ? 'The detailed Linux installer, Windows download, Docker command, release links, requirements, and troubleshooting notes live on a focused download page.'
            : 'Fabricator is free, self-hosted, and open source. Use the Linux installer, grab the Windows executable, or run the Docker image with persistent data in a volume.'}
        </p>
        <div className="mt-6 flex flex-wrap gap-3">
          <Link to="/download" className="inline-flex h-11 items-center gap-2 rounded-md bg-orange-500 px-4 text-sm font-bold text-black hover:bg-orange-400">
            {compact ? 'Open download page' : 'See downloads'} <ArrowRight className="h-4 w-4" />
          </Link>
          <a href="https://github.com/philderks/Fabricator/releases/latest" className="inline-flex h-11 items-center gap-2 rounded-md border border-white/10 bg-white/5 px-4 text-sm font-semibold text-white hover:bg-white/10">
            Latest GitHub release <ExternalLink className="h-4 w-4" />
          </a>
        </div>
      </div>
    </Section>
  );
}

export function HowSection() {
  return (
    <Section id="how" eyebrow="How it works" title="A straightforward path from install to first launch">
      <div className="grid gap-4 md:grid-cols-4">
        {workflow.map(([title, text], index) => (
          <article key={title} className="rounded-xl border border-white/10 bg-[#1b1b1b]/90 p-5 shadow-xl shadow-black/30">
            <span className="flex h-11 w-11 items-center justify-center rounded-xl border border-white/10 bg-orange-500/15 text-sm font-black text-orange-300">{index + 1}</span>
            <h3 className="mt-5 text-xl font-semibold">{title}</h3>
            <p className="mt-3 text-sm leading-7 text-zinc-400">{text}</p>
          </article>
        ))}
      </div>
    </Section>
  );
}

export function ScreenshotsSection() {
  const [api, setApi] = useState<CarouselApi>();
  const [selectedSlide, setSelectedSlide] = useState(0);
  const [isAutoPlaying, setIsAutoPlaying] = useState(true);

  const scrollToSlide = useCallback((index: number) => {
    api?.scrollTo(index);
  }, [api]);

  useEffect(() => {
    if (!api) return;

    const updateSelectedSlide = () => {
      setSelectedSlide(api.selectedScrollSnap());
    };

    updateSelectedSlide();
    api.on('select', updateSelectedSlide);
    api.on('reInit', updateSelectedSlide);

    return () => {
      api.off('select', updateSelectedSlide);
      api.off('reInit', updateSelectedSlide);
    };
  }, [api]);

  useEffect(() => {
    if (!api || !isAutoPlaying) return;

    const media = window.matchMedia('(prefers-reduced-motion: reduce)');
    if (media.matches) return;

    const interval = window.setInterval(() => {
      api.scrollNext();
    }, 6500);

    return () => window.clearInterval(interval);
  }, [api, isAutoPlaying, selectedSlide]);

  return (
    <Section id="shots" eyebrow="Inside the app" title="Core workflows inside the Fabricator control panel">
      <p className="max-w-3xl text-lg leading-8 text-zinc-400">
        Fabricator is built around the tasks Minecraft server admins repeat: status checks, player management, Modrinth installs, backups, and troubleshooting from the browser.
      </p>
      <div className="mx-auto mt-12 max-w-5xl">
        <Carousel
          opts={{ loop: true, align: 'start', duration: 38 }}
          setApi={setApi}
          className="px-0 md:px-10"
        >
          <CarouselContent>
            {screenshotCards.map((shot, index) => (
              <CarouselItem key={shot.title}>
                <div className="overflow-hidden rounded-xl border border-white/10 bg-[#1b1b1b] shadow-2xl shadow-black/50 ring-1 ring-transparent transition duration-500 ease-out hover:border-primary/35 hover:ring-primary/20">
                  <div className="flex items-center gap-3 border-b border-white/10 bg-[#111]/90 px-4 py-3">
                    <div className="flex gap-1.5">
                      <span className="h-2.5 w-2.5 rounded-full bg-red-500" />
                      <span className="h-2.5 w-2.5 rounded-full bg-yellow-400" />
                      <span className="h-2.5 w-2.5 rounded-full bg-green-500" />
                    </div>
                    <div className="min-w-0 flex-1 rounded-md bg-white/[0.06] px-3 py-1.5 font-mono text-xs text-zinc-500">
                      fabricator · {shot.title}
                    </div>
                  </div>
                  <div className="bg-[#101010]">
                    <img
                      src={shot.image}
                      alt={shot.alt}
                      width={1280}
                      height={657}
                      loading="lazy"
                      decoding="async"
                      className="h-auto w-full object-contain transition duration-700 ease-out motion-reduce:transition-none"
                    />
                  </div>
                  <div className="flex flex-col gap-3 border-t border-white/10 bg-[#101010]/80 p-5 transition duration-500 ease-out md:flex-row md:items-center md:justify-between">
                    <div className="transition-all duration-500 ease-out motion-reduce:transition-none">
                      <h3 className="text-lg font-semibold text-white">{shot.title}</h3>
                      <p className="mt-1 text-sm leading-6 text-zinc-400">{shot.text}</p>
                    </div>
                    <span className="rounded-full border border-primary/20 bg-primary/10 px-3 py-1 font-mono text-xs text-primary">{index + 1} / {screenshotCards.length}</span>
                  </div>
                </div>
              </CarouselItem>
            ))}
          </CarouselContent>
          <CarouselPrevious className="left-3 border-primary/25 bg-black/70 text-white ring-1 ring-transparent hover:border-primary/60 hover:bg-primary/15 hover:text-primary hover:ring-primary/20 md:left-0" />
          <CarouselNext className="right-3 border-primary/25 bg-black/70 text-white ring-1 ring-transparent hover:border-primary/60 hover:bg-primary/15 hover:text-primary hover:ring-primary/20 md:right-0" />
        </Carousel>
        <div className="mt-5 flex items-center justify-center gap-2" aria-label="Screenshot carousel navigation">
          <div className="flex items-center gap-2 rounded-full border border-white/10 bg-[#171717]/85 px-3 py-2 shadow-xl shadow-black/25">
          {screenshotCards.map((shot, index) => {
            const isSelected = selectedSlide === index;

            return (
              <button
                key={shot.title}
                type="button"
                aria-label={`Show screenshot ${index + 1}: ${shot.title}`}
                aria-current={isSelected ? 'true' : undefined}
                onClick={() => scrollToSlide(index)}
                className={`group h-2.5 rounded-full transition-all duration-300 ease-out focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-primary/40 ${
                  isSelected
                    ? 'w-8 bg-primary shadow-[0_0_18px_rgba(249,115,22,0.35)]'
                    : 'w-2.5 bg-zinc-700 hover:bg-primary/60'
                }`}
              >
                <span className="sr-only">{index + 1}</span>
              </button>
            );
          })}
            <span className="mx-1 h-4 w-px bg-white/10" aria-hidden="true" />
            <button
              type="button"
              aria-label={isAutoPlaying ? 'Pause screenshot auto-advance' : 'Resume screenshot auto-advance'}
              title={isAutoPlaying ? 'Pause auto-advance' : 'Resume auto-advance'}
              onClick={() => setIsAutoPlaying((current) => !current)}
              className="flex h-7 w-7 items-center justify-center rounded-full border border-white/10 bg-white/[0.04] text-zinc-400 transition hover:border-primary/50 hover:bg-primary/10 hover:text-primary focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-primary/40"
            >
              {isAutoPlaying ? <Pause className="h-3.5 w-3.5" /> : <Play className="h-3.5 w-3.5" />}
            </button>
          </div>
        </div>
      </div>
    </Section>
  );
}

export function FAQSection() {
  return (
    <section id="faq" className="scroll-mt-24 border-y border-white/10 bg-[radial-gradient(circle_at_50%_0%,rgba(234,88,12,0.08),transparent_34%),rgba(15,15,15,0.35)] px-5 py-16 md:py-24">
      <div className="mx-auto max-w-6xl">
        <h2 className="text-center text-4xl font-bold leading-tight md:text-6xl">Frequently Asked Questions</h2>
        <Accordion defaultValue={['faq-0']} className="mt-12 gap-4">
          {faqItems.map(([question, answer], index) => (
            <AccordionItem key={question} value={`faq-${index}`} className="rounded-xl border border-white/10 bg-[#1b1b1b]/80 px-5 shadow-xl shadow-black/30">
              <AccordionTrigger className="py-5 text-xl font-bold text-white hover:no-underline">
                {question}
              </AccordionTrigger>
              <AccordionContent className="border-t border-white/10 pb-5 pt-4 text-sm leading-7 text-zinc-400">
                {answer}
              </AccordionContent>
            </AccordionItem>
          ))}
        </Accordion>
      </div>
    </section>
  );
}

export function FeaturePage() {
  return (
    <>
      <PageHero eyebrow="Fabricator features" title="Everything for focused Minecraft server management" text="Fabricator keeps the day-to-day server-owner workflow in one self-hosted dashboard: create servers, install Modrinth content, manage players, track status, handle logs and files, and recover safely with backups." />
      <Section eyebrow="Full feature list" title="Built around Minecraft server workflows">
        <Tabs defaultValue={featureGroups[0].value} className="gap-8">
          <TabsList variant="line" className="flex h-auto w-full flex-wrap justify-start gap-2 rounded-none p-0">
            {featureGroups.map((group) => {
              const Icon = group.icon;

              return (
                <TabsTrigger
                  key={group.value}
                  value={group.value}
                  className="h-11 flex-none rounded-full border border-white/10 bg-white/[0.04] px-4 text-zinc-300 data-active:border-orange-500/50 data-active:bg-orange-500/15 data-active:text-orange-100"
                >
                  <Icon className="h-4 w-4" />
                  {group.eyebrow}
                </TabsTrigger>
              );
            })}
          </TabsList>
          {featureGroups.map((group) => (
            <TabsContent key={group.value} value={group.value}>
              <Card className="rounded-xl border-white/10 bg-[#1b1b1b]/90 text-white shadow-2xl shadow-black/35">
                <CardHeader className="p-6">
                  <div className="flex items-center gap-3">
                    <IconBadge icon={group.icon} />
                    <p className="text-xs font-bold uppercase text-orange-400">{group.eyebrow}</p>
                  </div>
                  <CardTitle className="mt-5 text-2xl font-semibold">{group.title}</CardTitle>
                  <CardDescription className="max-w-3xl text-sm leading-7 text-zinc-400">{group.text}</CardDescription>
                </CardHeader>
                <CardContent className="grid gap-3 px-6 pb-6 md:grid-cols-2">
                  {group.items.map(([title, text]) => (
                    <div key={title} className="rounded-xl border border-white/10 bg-black/20 p-4">
                      <h4 className="text-sm font-semibold">{title}</h4>
                      <p className="mt-2 text-sm leading-6 text-zinc-400">{text}</p>
                    </div>
                  ))}
                </CardContent>
              </Card>
            </TabsContent>
          ))}
        </Tabs>
      </Section>
    </>
  );
}

export function DownloadPage() {
  const [copiedCommand, setCopiedCommand] = useState<string | null>(null);

  const copyCommand = useCallback((command: string) => {
    void navigator.clipboard.writeText(command);
    setCopiedCommand(command);
    window.setTimeout(() => setCopiedCommand((current) => (current === command ? null : current)), 1800);
  }, []);

  return (
    <>
      <section className="mx-auto max-w-6xl px-5 py-16 text-center md:py-24">
        <Eyebrow>Download Fabricator</Eyebrow>
        <h1 className="mx-auto mt-4 max-w-4xl text-5xl font-bold leading-none md:text-7xl">Install Fabricator</h1>
        <p className="mx-auto mt-6 max-w-2xl text-lg leading-8 text-zinc-400">
          Pick your platform, grab the latest build, and get to the Fabricator dashboard in minutes.
        </p>
        <Tabs defaultValue="linux" className="mx-auto mt-10 max-w-5xl gap-10">
          <TabsList className="grid h-auto min-h-0 w-full grid-cols-1 gap-4 bg-transparent p-0 group-data-horizontal/tabs:h-auto group-data-horizontal/tabs:min-h-0 md:grid-cols-3">
            {platforms.map(({ value, name, icon: Icon }) => (
              <TabsTrigger
                key={value}
                value={value}
                className="h-auto min-h-28 rounded-2xl border border-white/10 bg-[#1b1b1b]/90 p-6 text-center text-white shadow-2xl shadow-black/30 transition hover:-translate-y-1 hover:border-primary/45 hover:ring-2 hover:ring-primary/15 data-active:border-primary data-active:bg-gradient-to-br data-active:from-primary data-active:to-orange-600 data-active:text-primary-foreground data-active:shadow-orange-950/35 sm:min-h-32 md:min-h-36"
              >
                <span className="grid justify-items-center gap-4">
                  <Icon className="h-10 w-10 sm:h-11 sm:w-11 md:h-12 md:w-12" />
                  <span className="text-lg font-bold md:text-xl">{name}</span>
                </span>
              </TabsTrigger>
            ))}
          </TabsList>
          {platforms.map((platform) => (
            <TabsContent key={platform.value} value={platform.value} className="mx-auto max-w-3xl">
              <div className="text-center">
                <p className="text-xs font-bold uppercase tracking-[0.24em] text-zinc-500">{platform.eyebrow}</p>
                <h2 className="mt-3 text-3xl font-bold">{platform.title}</h2>
                <span className="mt-3 inline-flex rounded-full border border-primary/30 bg-primary/15 px-3 py-1 text-xs font-bold text-primary">{platform.status}</span>
                <p className="mx-auto mt-4 max-w-xl text-sm leading-7 text-zinc-400">{platform.text}</p>
              </div>

              <dl className={`mx-auto mt-5 grid max-w-xl gap-2 text-left text-xs ${platform.meta.length > 2 ? 'grid-cols-2 md:grid-cols-4' : 'grid-cols-2 md:max-w-xs'}`}>
                {platform.meta.map(([label, value]) => (
                  <div key={label} className="rounded-xl border border-white/10 bg-[#151515]/90 px-4 py-3">
                    <dt className="font-bold uppercase tracking-[0.16em] text-zinc-500">{label}</dt>
                    <dd className="mt-1 truncate font-semibold text-white">{value}</dd>
                  </div>
                ))}
              </dl>

              <div className="mx-auto mt-5 max-w-2xl rounded-2xl border border-white/10 bg-[#1b1b1b]/90 p-3 shadow-2xl shadow-black/35 ring-1 ring-transparent transition hover:border-primary/35 hover:ring-primary/15">
                {platform.command ? (
                  <div className="grid gap-3 md:grid-cols-[1fr_auto] md:items-center">
                    <code className="block overflow-x-auto rounded-xl bg-black/55 px-4 py-3 text-left font-mono text-sm text-zinc-200">
                      {platform.command}
                    </code>
                    <button
                      type="button"
                      onClick={() => copyCommand(platform.command!)}
                      className="group inline-flex h-11 items-center justify-center gap-2 rounded-full bg-primary px-5 text-sm font-bold text-primary-foreground shadow-lg shadow-orange-950/25 transition hover:bg-orange-400 focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-primary/40"
                    >
                      <span className="relative h-4 w-4" aria-hidden="true">
                        <Copy
                          className={`absolute inset-0 h-4 w-4 transition duration-200 ease-out ${
                            copiedCommand === platform.command
                              ? 'scale-50 rotate-6 opacity-0'
                              : 'scale-100 rotate-0 opacity-100'
                          }`}
                        />
                        <Check
                          className={`absolute inset-0 h-4 w-4 transition duration-200 ease-out ${
                            copiedCommand === platform.command
                              ? 'scale-100 rotate-0 opacity-100'
                              : 'scale-50 -rotate-6 opacity-0'
                          }`}
                        />
                      </span>
                      <span aria-live="polite">{copiedCommand === platform.command ? 'Copied' : 'Copy'}</span>
                    </button>
                  </div>
                ) : platform.primaryAction ? (
                  <div className="flex flex-col items-center gap-4 py-4">
                    <a href={platform.primaryAction[1]} className="inline-flex h-11 items-center justify-center gap-2 rounded-full bg-primary px-5 text-sm font-bold text-primary-foreground shadow-lg shadow-orange-950/25 transition hover:bg-orange-400">
                      <Download className="h-4 w-4" />
                      {platform.primaryAction[0]}
                    </a>
                    <p className="text-sm text-zinc-400">Pulled from the latest GitHub release.</p>
                  </div>
                ) : null}

                {platform.note ? (
                  <p className="mt-3 rounded-xl border border-white/10 bg-black/25 px-4 py-3 text-left font-mono text-xs leading-6 text-zinc-500">
                    {platform.note}
                  </p>
                ) : null}
              </div>

              <div className="mt-4 flex flex-wrap justify-center gap-4">
                {platform.links.map(([label, href]) => (
                  <a key={label} href={href} className="inline-flex items-center gap-1.5 text-sm font-semibold text-zinc-400 underline decoration-white/15 underline-offset-4 transition hover:text-primary hover:decoration-primary/60">
                    {label} <ExternalLink className="h-3.5 w-3.5" />
                  </a>
                ))}
              </div>
            </TabsContent>
          ))}
        </Tabs>
      </section>
    </>
  );
}

export function LegalMdxPage({
  eyebrow,
  title,
  intro,
  children,
}: {
  eyebrow: string;
  title: string;
  intro: string;
  children: ReactNode;
}) {
  return (
    <section className="mx-auto max-w-4xl px-5 py-16 md:py-24">
      <Link to="/" className="mb-8 inline-flex items-center gap-2 text-sm font-semibold text-orange-300">
        <ArrowRight className="h-4 w-4 rotate-180" /> Back to Fabricator
      </Link>
      <Eyebrow>{eyebrow}</Eyebrow>
      <h1 className="mt-4 text-4xl font-bold md:text-6xl">{title}</h1>
      <p className="mt-5 text-lg leading-8 text-zinc-400">{intro}</p>
      <article className="legal-mdx mt-10 rounded-xl border border-white/10 bg-[#1b1b1b]/90 p-6 text-zinc-400 shadow-xl shadow-black/30 md:p-8">
        {children}
      </article>
    </section>
  );
}
function PageHero({
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
    <section className={`mx-auto max-w-6xl px-5 py-16 md:py-24 ${centered ? 'text-center' : ''}`}>
      <Eyebrow>{eyebrow}</Eyebrow>
      <h1 className={`mt-4 text-4xl font-bold leading-tight md:text-6xl ${centered ? 'mx-auto max-w-4xl' : 'max-w-4xl'}`}>{title}</h1>
      <p className={`mt-5 text-lg leading-8 text-zinc-400 ${centered ? 'mx-auto max-w-2xl' : 'max-w-3xl'}`}>{text}</p>
      <div className={`mt-8 flex flex-wrap gap-3 ${centered ? 'justify-center' : ''}`}>
        <MarketingRouteLink href="/download" className="inline-flex h-11 items-center gap-2 rounded-md bg-orange-500 px-4 text-sm font-bold text-black hover:bg-orange-400">
          Download Fabricator <Download className="h-4 w-4" />
        </MarketingRouteLink>
        <MarketingRouteLink href="/docs" className="inline-flex h-11 items-center gap-2 rounded-md border border-white/10 px-4 text-sm font-semibold text-zinc-200 hover:bg-white/5">
          Read the docs <ArrowRight className="h-4 w-4" />
        </MarketingRouteLink>
      </div>
    </section>
  );
}

function Section({
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
    <section id={id} className="mx-auto max-w-6xl scroll-mt-24 px-5 py-14 md:py-20">
      {eyebrow ? <Eyebrow>{eyebrow}</Eyebrow> : null}
      {title ? <h2 className="mt-3 max-w-4xl text-3xl font-bold leading-tight md:text-5xl">{title}</h2> : null}
      <div className={title || eyebrow ? 'mt-8' : undefined}>{children}</div>
    </section>
  );
}

function MiniFeature({ icon, title, text }: { icon: LucideIcon; title: string; text: string }) {
  return (
    <article className="rounded-xl border border-white/10 bg-[#1b1b1b]/90 p-5 shadow-xl shadow-black/25">
      <IconBadge icon={icon} />
      <h3 className="mt-5 text-xl font-semibold">{title}</h3>
      <p className="mt-3 text-sm leading-7 text-zinc-400">{text}</p>
    </article>
  );
}

function IconBadge({ icon: Icon }: { icon: LucideIcon }) {
  return (
    <span className="flex h-10 w-10 items-center justify-center rounded-xl border border-white/10 bg-orange-500/15 text-orange-300">
      <Icon className="h-5 w-5" />
    </span>
  );
}

function Eyebrow({ children }: { children: ReactNode }) {
  return <p className="text-xs font-black uppercase text-orange-400">{children}</p>;
}

function FabricatorMark() {
  return (
    <img src="/favicon.svg" alt="" width={32} height={32} className="h-8 w-8" />
  );
}
