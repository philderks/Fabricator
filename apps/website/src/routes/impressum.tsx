import { createFileRoute } from "@tanstack/react-router";
import { LegalMdxLayout } from "@/components/marketing/layouts/legal-mdx-layout";
import { MarketingLayout } from "@/components/marketing/layouts/marketing-layout";
import ImpressumContent from "@/content/legal/impressum.mdx";

export const Route = createFileRoute("/impressum")({
  head: () => ({
    meta: [
      { title: "Legal Notice | Fabricator" },
      {
        name: "description",
        content:
          "Legal notice and operator information for the Fabricator website.",
      },
    ],
  }),
  component: Impressum,
});

function Impressum() {
  return (
    <MarketingLayout active="impressum" legal>
      <LegalMdxLayout
        eyebrow="Legal"
        title="Legal Notice"
        intro="Information about the operator of fabricator.site."
      >
        <ImpressumContent />
      </LegalMdxLayout>
    </MarketingLayout>
  );
}
