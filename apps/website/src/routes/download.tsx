import { createFileRoute } from '@tanstack/react-router';
import { DownloadPage, MarketingLayout } from '@/components/marketing';

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
  component: Download,
});

function Download() {
  return (
    <MarketingLayout active="download">
      <DownloadPage />
    </MarketingLayout>
  );
}
