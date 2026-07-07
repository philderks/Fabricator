import type { LucideIcon } from 'lucide-react';
import {
  Boxes,
  HardDrive,
  Monitor,
  RotateCcw,
  Server,
  TerminalSquare,
} from 'lucide-react';

export type ActivePage = 'home' | 'features' | 'download' | 'privacy' | 'impressum';
export type MarketingHomeSection = 'how' | 'shots' | 'faq' | null;
export type MarketingLink = readonly [label: string, href: string];
export type MarketingFeatureItem = readonly [title: string, text: string];
export type MarketingNavItem = {
  label: string;
  href: string;
  active: ActivePage | 'docs';
  cta?: boolean;
};

export type MarketingFeatureGroup = {
  value: string;
  eyebrow: string;
  icon: LucideIcon;
  title: string;
  text: string;
  items: MarketingFeatureItem[];
};

export type MarketingScreenshot = {
  title: string;
  text: string;
  image: string;
  alt: string;
};

export type MarketingPlatform = {
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

export const release = {
  version: 'v0.9.2',
  date: 'Jul 3, 2026',
};

export const navItems: MarketingNavItem[] = [
  { label: 'Features', href: '/features', active: 'features' },
  { label: 'Download', href: '/download', active: 'download', cta: true },
  { label: 'How it works', href: '/#how', active: 'home' },
  { label: 'Inside the app', href: '/#shots', active: 'home' },
  { label: 'FAQ', href: '/#faq', active: 'home' },
  { label: 'Docs', href: '/docs', active: 'docs' },
];

export const featureGroups: MarketingFeatureGroup[] = [
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

export const platforms: MarketingPlatform[] = [
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

export const workflow = [
  ['Install Fabricator', 'Run the Linux installer, Windows executable, or Docker image on the machine you want to host or manage, then open the web UI.'],
  ['Create your Minecraft server', 'Choose a name, Minecraft version, loader, port, and install path. Fabricator checks Java requirements before setup.'],
  ['Add mods or a modpack from Modrinth', 'Install content from Modrinth, then adjust files and settings from the dashboard.'],
  ['Run, monitor, and back it up', 'Start or restart the server, watch logs and metrics, manage players, browse files, and create backups before risky changes.'],
] as const;

export const screenshotCards: MarketingScreenshot[] = [
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

export const faqItems = [
  ['Is Fabricator free and open source?', 'Yes. Fabricator is free to use, self-hosted, and open source, with the source code available on GitHub.'],
  ['What modloaders does Fabricator support?', 'Fabricator supports Fabric, Quilt, NeoForge, Forge, and Vanilla Java Edition server workflows.'],
  ['Does Fabricator support Bedrock servers?', 'Fabricator is focused on Java Edition servers. Bedrock support is not part of the current scope.'],
  ['Can Fabricator install mods and modpacks from Modrinth?', 'Yes. Modrinth search, compatibility checks, and install actions are part of the core workflow.'],
  ['How does it compare with Crafty, Pterodactyl, or Docker?', 'Fabricator is simpler than hosting panels and more guided than raw container workflows. It is meant for personal servers and small communities.'],
  ['Can Fabricator manage players?', 'Yes. You can review known and online players, operators, whitelist entries, bans, IP bans, and kicks.'],
  ['How do I install Fabricator?', 'Use the Linux installer, Windows executable, or Docker image from the download page.'],
] as const;
