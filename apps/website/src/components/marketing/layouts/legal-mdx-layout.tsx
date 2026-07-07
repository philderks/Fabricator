import { Link } from '@tanstack/react-router';
import { ArrowRight } from 'lucide-react';
import type { ReactNode } from 'react';
import { Eyebrow } from '../shared';

export function LegalMdxLayout({
  eyebrow,
  title,
  intro,
  children,
}: {
  eyebrow: string;
  title: string;
  intro: string;
  children: ReactNode;
}) {
  return (
    <section className="mx-auto max-w-4xl px-5 py-16 md:py-24">
      <Link to="/" className="mb-8 inline-flex items-center gap-2 text-sm font-semibold text-orange-300">
        <ArrowRight className="h-4 w-4 rotate-180" /> Back to Fabricator
      </Link>
      <Eyebrow>{eyebrow}</Eyebrow>
      <h1 className="mt-4 text-4xl font-bold md:text-6xl">{title}</h1>
      <p className="mt-5 text-lg leading-8 text-zinc-400">{intro}</p>
      <article className="legal-mdx mt-10 rounded-xl border border-white/10 bg-[#1b1b1b]/90 p-6 text-zinc-400 shadow-xl shadow-black/30 md:p-8">
        {children}
      </article>
    </section>
  );
}
