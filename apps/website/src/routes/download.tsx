import { createFileRoute } from '@tanstack/react-router';
import {  MarketingLayout } from '@/components/marketing/layouts/marketing-layout';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Check, Copy, Download, ExternalLink } from 'lucide-react';
import { useCallback, useState } from 'react';
import { platforms } from '@/components/marketing/data';
import { Eyebrow } from '@/components/marketing/shared';


export const Route = createFileRoute('/download')({
  head: () => ({
    meta: [
      { title: 'Download Fabricator | Linux, Windows & Docker Minecraft Server Manager' },
      {
        name: 'description',
        content:
          'Install Fabricator on Linux, download the Windows build, or run the Docker image for self-hosted Minecraft server management.',
      },
    ],
  }),
  component: DownloadPage,
});

function DownloadPage() {
    const [copiedCommand, setCopiedCommand] = useState<string | null>(null);

  const copyCommand = useCallback((command: string) => {
    void navigator.clipboard.writeText(command);
    setCopiedCommand(command);
    window.setTimeout(() => setCopiedCommand((current) => (current === command ? null : current)), 1800);
  }, []);
  return (
    <MarketingLayout active="download">
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
    </MarketingLayout>
  );
}
