'use client';

import { Check, LinkIcon } from 'lucide-react';
import { type ComponentProps, type ReactNode, useEffect, useRef, useState } from 'react';
import { cn } from '../lib/cn';
import { useCopyButton } from 'fumadocs-ui/utils/use-copy-button';
import { buttonVariants } from './ui/button';
import { mergeRefs } from '../lib/merge-refs';
import { useTranslations } from '@fuma-translate/react';
import {
  Accordion as Root,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from './ui/accordion';

type AccordionsProps = Omit<
  ComponentProps<typeof Root>,
  'defaultValue' | 'multiple' | 'onValueChange' | 'value'
> & {
  type?: 'single' | 'multiple';
  defaultValue?: string | string[];
};

export function Accordions({
  type = 'single',
  ref,
  className,
  defaultValue,
  ...props
}: AccordionsProps) {
  const rootRef = useRef<HTMLDivElement>(null);
  const composedRef = mergeRefs(ref, rootRef);
  const [value, setValue] = useState<string[]>(() =>
    Array.isArray(defaultValue) ? defaultValue : defaultValue ? [defaultValue] : [],
  );

  useEffect(() => {
    const id = window.location.hash.substring(1);
    const element = rootRef.current;
    if (!element || id.length === 0) return;

    const selected = document.getElementById(id);
    if (!selected || !element.contains(selected)) return;
    const value = selected.getAttribute('data-accordion-value');

    if (value) setValue((prev) => (type === 'single' ? [value] : [value, ...prev]));
  }, [type]);

  return (
    <Root
      ref={composedRef}
      multiple={type === 'multiple'}
      value={value}
      onValueChange={(nextValue) => {
        setValue(type === 'single' ? nextValue.slice(-1) : nextValue);
      }}
      className={cn(
        'divide-y divide-fd-border overflow-hidden rounded-lg border bg-fd-card',
        className,
      )}
      {...props}
    />
  );
}

export function Accordion({
  title,
  id,
  value = String(title),
  children,
  ...props
}: Omit<ComponentProps<typeof AccordionItem>, 'value' | 'title'> & {
  title: string | ReactNode;
  value?: string;
}) {
  return (
    <AccordionItem value={value} {...props}>
      <div id={id} className="flex items-start" data-accordion-value={value}>
        <AccordionTrigger className="px-4">{title}</AccordionTrigger>
        {id ? <CopyButton id={id} /> : null}
      </div>
      <AccordionContent>
        <div className="px-4 pb-2 text-[0.9375rem] prose-no-margin">{children}</div>
      </AccordionContent>
    </AccordionItem>
  );
}

function CopyButton({ id }: { id: string }) {
  const t = useTranslations({ note: 'accordion' });
  const [checked, onClick] = useCopyButton(() => {
    const url = new URL(window.location.href);
    url.hash = id;

    return navigator.clipboard.writeText(url.toString());
  });

  return (
    <button
      type="button"
      aria-label={t('Copy Link', { note: 'aria-label' })}
      className={cn(
        buttonVariants({
          variant: 'ghost',
          size: 'icon-sm',
          className: 'text-fd-muted-foreground me-2',
        }),
      )}
      onClick={onClick}
    >
      {checked ? <Check className="size-3.5" /> : <LinkIcon className="size-3.5" />}
    </button>
  );
}
