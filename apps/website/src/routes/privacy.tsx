import { createFileRoute } from '@tanstack/react-router';
import { LegalMdxPage, MarketingLayout } from '@/components/marketing';
import PrivacyContent from '@/content/legal/privacy.mdx';

export const Route = createFileRoute('/privacy')({
  head: () => ({
    meta: [
      { title: 'Privacy Policy | Fabricator' },
      {
        name: 'description',
        content: 'Privacy policy for fabricator.site and the Fabricator website.',
      },
    ],
  }),
  component: Privacy,
});

function Privacy() {
  return (
    <MarketingLayout active="privacy" legal>
      <LegalMdxPage
        eyebrow="Privacy"
        title="Privacy Policy"
        intro="This privacy policy explains which personal data may be processed when you visit fabricator.site."
      >
        <PrivacyContent />
      </LegalMdxPage>
    </MarketingLayout>
  );
}
