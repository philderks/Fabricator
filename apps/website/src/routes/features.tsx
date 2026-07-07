import { createFileRoute } from '@tanstack/react-router';
import { FeaturePage, MarketingLayout } from '@/components/marketing';

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
  component: Features,
});

function Features() {
  return (
    <MarketingLayout active="features">
      <FeaturePage />
    </MarketingLayout>
  );
}
