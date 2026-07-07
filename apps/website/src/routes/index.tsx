import { createFileRoute } from '@tanstack/react-router';
import {
  ComparisonSection,
  EcosystemSection,
  FAQSection,
  HeroSection,
  HowSection,
  MarketingLayout,
  ReadySection,
  ScreenshotsSection,
  WhySection,
} from '@/components/marketing';

export const Route = createFileRoute('/')({
  head: () => ({
    meta: [
      { title: 'Fabricator | Self-Hosted Minecraft Server Manager' },
      {
        name: 'description',
        content:
          'Create and manage Minecraft servers, mods, players, files, logs, metrics, and backups from one self-hosted dashboard.',
      },
    ],
  }),
  component: Home,
});

function Home() {
  return (
    <MarketingLayout active="home">
      <HeroSection />
      <WhySection />
      <ComparisonSection />
      <EcosystemSection />
      <ReadySection compact />
      <HowSection />
      <ScreenshotsSection />
      <FAQSection />
      <ReadySection />
    </MarketingLayout>
  );
}
