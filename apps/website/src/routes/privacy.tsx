import { createFileRoute } from "@tanstack/react-router";
import { LegalMdxLayout } from "@/components/marketing/layouts/legal-mdx-layout";
import { MarketingLayout } from "@/components/marketing/layouts/marketing-layout";
import PrivacyContent from "@/content/legal/privacy.mdx";

export const Route = createFileRoute("/privacy")({
  head: () => ({
    meta: [
      { title: "Privacy Policy | Fabricator" },
      {
        name: "description",
        content:
          "Privacy policy for fabricator.site and the Fabricator website.",
      },
    ],
  }),
  component: Privacy,
});

function Privacy() {
  return (
    <MarketingLayout active="privacy" legal>
      <LegalMdxLayout
        eyebrow="Privacy"
        title="Privacy Policy"
        intro="This privacy policy explains which personal data may be processed when you visit fabricator.site."
      >
        <PrivacyContent />
      </LegalMdxLayout>
    </MarketingLayout>
  );
}
