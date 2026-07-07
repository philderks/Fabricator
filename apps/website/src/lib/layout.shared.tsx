import type { BaseLayoutProps } from 'fumadocs-ui/layouts/shared';
import { appName, gitConfig } from './shared';

export function baseOptions(): BaseLayoutProps {
  return {
    nav: {
      title: (
        <a href="/" className="inline-flex items-center gap-2 font-semibold">
          <img src="/favicon.svg" alt="" width={24} height={24} className="h-6 w-6" />
          <span>{appName}</span>
        </a>
      ),
    },
    links: [
      {
        type: 'main',
        text: 'Home',
        url: '/',
      },
      {
        type: 'main',
        text: 'Features',
        url: '/features',
      },
      {
        type: 'main',
        text: 'Download',
        url: '/download',
      },
      {
        type: 'main',
        text: 'Docs',
        url: '/docs',
        active: 'nested-url',
      },
      {
        type: 'main',
        text: 'Install',
        url: '/docs/getting-started/installation',
        active: 'nested-url',
      },
    ],
    githubUrl: `https://github.com/${gitConfig.user}/${gitConfig.repo}`,
  };
}
