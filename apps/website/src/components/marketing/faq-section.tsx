import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from '@/components/ui/accordion';
import { faqItems } from '../data';

export function FAQSection() {
  return (
    <section id="faq" className="scroll-mt-24 border-y border-white/10 bg-[radial-gradient(circle_at_50%_0%,rgba(234,88,12,0.08),transparent_34%),rgba(15,15,15,0.35)] px-5 py-16 md:py-24">
      <div className="mx-auto max-w-6xl">
        <h2 className="text-center text-4xl font-bold leading-tight md:text-6xl">Frequently Asked Questions</h2>
        <Accordion defaultValue={['faq-0']} className="mt-12 gap-4">
          {faqItems.map(([question, answer], index) => (
            <AccordionItem key={question} value={`faq-${index}`} className="rounded-xl border border-white/10 bg-[#1b1b1b]/80 px-5 shadow-xl shadow-black/30">
              <AccordionTrigger className="py-5 text-xl font-bold text-white hover:no-underline">
                {question}
              </AccordionTrigger>
              <AccordionContent className="border-t border-white/10 pb-5 pt-4 text-sm leading-7 text-zinc-400">
                {answer}
              </AccordionContent>
            </AccordionItem>
          ))}
        </Accordion>
      </div>
    </section>
  );
}
