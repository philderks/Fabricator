import { createFileRoute } from '@tanstack/react-router';
import {  MarketingLayout } from '@/components/marketing/layouts/marketing-layout';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { featureGroups } from '@/components/marketing/data';
import { IconBadge, PageHero, Section } from '@/components/marketing/shared';


export const Route = createFileRoute('/features')({
  head: () => ({
    meta: [
      { title: 'Fabricator Features | Modrinth-Aware Minecraft Server Manager' },
      {
        name: 'description',
        content:
          'Explore Fabricator features for Minecraft server setup, Modrinth installs, player management, files, logs, tunnels, backups, and restore.',
      },
    ],
  }),
  component: FeaturePage,
});

function FeaturePage() {
  return (
    <MarketingLayout active="features">
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
    </MarketingLayout>
  );
}
