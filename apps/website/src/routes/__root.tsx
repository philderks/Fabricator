import { createRootRoute, HeadContent, Outlet, Scripts } from '@tanstack/react-router';
import { useLocation } from '@tanstack/react-router';
import * as React from 'react';
import appCss from '@/styles/app.css?url';
import { RootProvider } from 'fumadocs-ui/provider/tanstack';
import SearchDialog from '@/components/search';

export const Route = createRootRoute({
  head: () => ({
    meta: [
      {
        charSet: 'utf-8',
      },
      {
        name: 'viewport',
        content: 'width=device-width, initial-scale=1',
      },
      {
        title: 'Fabricator Docs',
      },
      {
        name: 'description',
        content: 'Self-hosted Minecraft server management dashboard documentation.',
      },
    ],
    links: [
      { rel: 'stylesheet', href: appCss },
      { rel: 'icon', href: '/favicon.svg', type: 'image/svg+xml' },
    ],
  }),
  component: RootComponent,
});

function RootComponent() {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <HeadContent />
      </head>
      <body className="flex flex-col min-h-screen">
        <RootProvider search={{ SearchDialog }} theme={{ defaultTheme: 'dark', enableSystem: true }}>
          <HashScroller />
          <Outlet />
        </RootProvider>
        <Scripts />
      </body>
    </html>
  );
}

function HashScroller() {
  const location = useLocation();

  React.useEffect(() => {
    if (typeof window === 'undefined') return;

    const hash = window.location.hash.slice(1);
    if (!hash) return;

    window.requestAnimationFrame(() => {
      const target = document.getElementById(hash);
      target?.scrollIntoView({ block: 'start', behavior: 'auto' });
    });
  }, [location.href]);

  return null;
}
