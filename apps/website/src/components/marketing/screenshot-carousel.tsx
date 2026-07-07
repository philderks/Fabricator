import {
  Carousel,
  type CarouselApi,
  CarouselContent,
  CarouselItem,
  CarouselNext,
  CarouselPrevious,
} from "@/components/ui/carousel";
import { Pause, Play } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { screenshotCards } from "./data";
import { Section } from "./shared";

export function ScreenshotCarousel() {
  const [api, setApi] = useState<CarouselApi>();
  const [selectedSlide, setSelectedSlide] = useState(0);
  const [isAutoPlaying, setIsAutoPlaying] = useState(true);

  const scrollToSlide = useCallback(
    (index: number) => {
      api?.scrollTo(index);
    },
    [api]
  );

  useEffect(() => {
    if (!api) return;

    const updateSelectedSlide = () => {
      setSelectedSlide(api.selectedScrollSnap());
    };

    updateSelectedSlide();
    api.on("select", updateSelectedSlide);
    api.on("reInit", updateSelectedSlide);

    return () => {
      api.off("select", updateSelectedSlide);
      api.off("reInit", updateSelectedSlide);
    };
  }, [api]);

  useEffect(() => {
    if (!api || !isAutoPlaying) return;

    const media = window.matchMedia("(prefers-reduced-motion: reduce)");
    if (media.matches) return;

    const interval = window.setInterval(() => {
      api.scrollNext();
    }, 6500);

    return () => window.clearInterval(interval);
  }, [api, isAutoPlaying, selectedSlide]);

  return (
    <Section
      id="shots"
      eyebrow="Inside the app"
      title="Core workflows inside the Fabricator control panel"
    >
      <p className="max-w-3xl text-lg leading-8 text-zinc-400">
        Fabricator is built around the tasks Minecraft server admins repeat:
        status checks, player management, Modrinth installs, backups, and
        troubleshooting from the browser.
      </p>
      <div className="mx-auto mt-12 max-w-5xl">
        <Carousel
          opts={{ loop: true, align: "start", duration: 38 }}
          setApi={setApi}
          className="px-0 md:px-10"
        >
          <CarouselContent>
            {screenshotCards.map((shot, index) => (
              <CarouselItem key={shot.title}>
                <div className="overflow-hidden rounded-xl border border-white/10 bg-[#1b1b1b] shadow-2xl shadow-black/50 ring-1 ring-transparent transition duration-500 ease-out hover:border-primary/35 hover:ring-primary/20">
                  <div className="flex items-center gap-3 border-b border-white/10 bg-[#111]/90 px-4 py-3">
                    <div className="flex gap-1.5">
                      <span className="h-2.5 w-2.5 rounded-full bg-red-500" />
                      <span className="h-2.5 w-2.5 rounded-full bg-yellow-400" />
                      <span className="h-2.5 w-2.5 rounded-full bg-green-500" />
                    </div>
                    <div className="min-w-0 flex-1 rounded-md bg-white/[0.06] px-3 py-1.5 font-mono text-xs text-zinc-500">
                      fabricator · {shot.title}
                    </div>
                  </div>
                  <div className="bg-[#101010]">
                    <img
                      src={shot.image}
                      alt={shot.alt}
                      width={1280}
                      height={657}
                      loading="lazy"
                      decoding="async"
                      className="h-auto w-full object-contain transition duration-700 ease-out motion-reduce:transition-none"
                    />
                  </div>
                  <div className="flex flex-col gap-3 border-t border-white/10 bg-[#101010]/80 p-5 transition duration-500 ease-out md:flex-row md:items-center md:justify-between">
                    <div className="transition-all duration-500 ease-out motion-reduce:transition-none">
                      <h3 className="text-lg font-semibold text-white">
                        {shot.title}
                      </h3>
                      <p className="mt-1 text-sm leading-6 text-zinc-400">
                        {shot.text}
                      </p>
                    </div>
                    <span className="rounded-full border border-primary/20 bg-primary/10 px-3 py-1 font-mono text-xs text-primary">
                      {index + 1} / {screenshotCards.length}
                    </span>
                  </div>
                </div>
              </CarouselItem>
            ))}
          </CarouselContent>
          <CarouselPrevious className="left-3 border-primary/25 bg-black/70 text-white ring-1 ring-transparent hover:border-primary/60 hover:bg-primary/15 hover:text-primary hover:ring-primary/20 md:left-0" />
          <CarouselNext className="right-3 border-primary/25 bg-black/70 text-white ring-1 ring-transparent hover:border-primary/60 hover:bg-primary/15 hover:text-primary hover:ring-primary/20 md:right-0" />
        </Carousel>
        <div
          className="mt-5 flex items-center justify-center gap-2"
          aria-label="Screenshot carousel navigation"
        >
          <div className="flex items-center gap-2 rounded-full border border-white/10 bg-[#171717]/85 px-3 py-2 shadow-xl shadow-black/25">
            {screenshotCards.map((shot, index) => {
              const isSelected = selectedSlide === index;

              return (
                <button
                  key={shot.title}
                  type="button"
                  aria-label={`Show screenshot ${index + 1}: ${shot.title}`}
                  aria-current={isSelected ? "true" : undefined}
                  onClick={() => scrollToSlide(index)}
                  className={`group h-2.5 rounded-full transition-all duration-300 ease-out focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-primary/40 ${
                    isSelected
                      ? "w-8 bg-primary shadow-[0_0_18px_rgba(249,115,22,0.35)]"
                      : "w-2.5 bg-zinc-700 hover:bg-primary/60"
                  }`}
                >
                  <span className="sr-only">{index + 1}</span>
                </button>
              );
            })}
            <span className="mx-1 h-4 w-px bg-white/10" aria-hidden="true" />
            <button
              type="button"
              aria-label={
                isAutoPlaying
                  ? "Pause screenshot auto-advance"
                  : "Resume screenshot auto-advance"
              }
              title={
                isAutoPlaying ? "Pause auto-advance" : "Resume auto-advance"
              }
              onClick={() => setIsAutoPlaying((current) => !current)}
              className="flex h-7 w-7 items-center justify-center rounded-full border border-white/10 bg-white/[0.04] text-zinc-400 transition hover:border-primary/50 hover:bg-primary/10 hover:text-primary focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-primary/40"
            >
              {isAutoPlaying ? (
                <Pause className="h-3.5 w-3.5" />
              ) : (
                <Play className="h-3.5 w-3.5" />
              )}
            </button>
          </div>
        </div>
      </div>
    </Section>
  );
}
