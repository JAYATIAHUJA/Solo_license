import { useLayoutEffect, useRef } from 'react';
import gsap from 'gsap';
import { ScrollTrigger } from 'gsap/ScrollTrigger';
import './landing.css';

gsap.registerPlugin(ScrollTrigger);

const Arrow = () => <svg aria-hidden="true" viewBox="0 0 20 20" className="h-4 w-4 fill-none stroke-current stroke-[1.8]"><path d="M4 10h11M11 5l5 5-5 5" strokeLinecap="round" strokeLinejoin="round" /></svg>;

const Mark = () => <span className="grid h-8 w-8 place-items-center rounded-[9px] bg-[#161916] text-sm font-bold text-white">S</span>;

function NavLink({ href, children }: { href: string; children: string }) {
  return <a className="text-[13px] font-medium text-neutral-500 transition-colors hover:text-neutral-950" href={href}>{children}</a>;
}

export function LandingPage() {
  const pageRef = useRef<HTMLElement>(null);

  useLayoutEffect(() => {
    document.documentElement.dataset.landing = 'true';
    const context = gsap.context(() => {
      const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
      if (reduceMotion) return;
      gsap.from('.hero-copy', { y: 42, opacity: 0, duration: 1.1, ease: 'power3.out' });
      gsap.from('.hero-visual', { y: 55, scale: 0.96, opacity: 0, duration: 1.2, delay: 0.1, ease: 'power3.out' });
      gsap.from('.hero-proof', { x: 36, opacity: 0, duration: 0.9, delay: 0.28, ease: 'power3.out' });
      gsap.to('.hero-visual', { yPercent: 12, scale: 1.08, ease: 'none', scrollTrigger: { trigger: '.landing-hero', start: 'top top', end: 'bottom top', scrub: 1 } });
      gsap.to('.hero-copy', { yPercent: -16, ease: 'none', scrollTrigger: { trigger: '.landing-hero', start: 'top top', end: 'bottom top', scrub: 1 } });
      gsap.utils.toArray<HTMLElement>('.section-reveal').forEach((element) => {
        gsap.from(element, { y: 40, opacity: 0, duration: 0.8, ease: 'power3.out', scrollTrigger: { trigger: element, start: 'top 82%', once: true } });
      });
    }, pageRef);
    return () => {
      context.revert();
      delete document.documentElement.dataset.landing;
    };
  }, []);

  return <main ref={pageRef} className="landing-page min-h-screen overflow-x-hidden">
    <div className="soft-grain pointer-events-none fixed inset-0 z-50 opacity-[0.025] mix-blend-multiply" />
    <nav className="relative z-20 mx-auto flex h-[82px] w-full max-w-[1440px] items-center justify-between px-7 md:px-12">
      <a href="/landing" className="flex items-center gap-2.5 font-display text-[17px] font-semibold tracking-[-0.04em]"><Mark /> Solo License</a>
      <div className="hidden items-center gap-9 md:flex"><NavLink href="#workflow">How it works</NavLink><NavLink href="#autonomy">Autonomy</NavLink><NavLink href="#evidence">Evidence</NavLink></div>
      <a href="/" className="inline-flex items-center gap-2 rounded-full bg-[#161916] px-4 py-2.5 text-[13px] font-semibold text-white transition hover:bg-[#2cbf65]">Open product <Arrow /></a>
    </nav>

    <section className="landing-hero relative min-h-[760px] overflow-hidden px-7 pb-16 pt-12 md:min-h-[calc(100svh-82px)] md:px-12 md:pt-20">
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_70%_40%,rgba(59,207,111,0.17),transparent_25%),linear-gradient(180deg,#fff_0%,#f9fcfa_100%)]" />
      <div className="pointer-events-none absolute inset-x-0 bottom-0 h-[58%] opacity-60 [background:repeating-radial-gradient(ellipse_at_50%_110%,transparent_0_84px,rgba(20,22,20,0.065)_85px_86px)]" />
      <div className="relative z-10 mx-auto grid max-w-[1280px] items-center gap-8 lg:grid-cols-[0.9fr_1fr_0.65fr] lg:gap-0">
        <div className="hero-copy max-w-[470px] pt-5 lg:pt-0">
          <h1 className="font-display text-[clamp(3.5rem,5.3vw,5.85rem)] font-semibold leading-[0.91] tracking-[-0.085em] text-[#161916]">Autonomy<br />you <span className="font-serif font-normal italic text-[#29b85d]">earn,</span><br />not autonomy<br />you assume.</h1>
          <p className="mt-7 max-w-[39ch] text-[16px] leading-7 text-neutral-600">A refund agent that earns the right to act unattended through verified clean runs, then loses it the instant a detection fires.</p>
          <div className="mt-8 flex flex-wrap gap-3"><a href="/" className="inline-flex items-center gap-2 rounded-full bg-[#161916] px-5 py-3 text-sm font-semibold text-white transition hover:bg-[#29b85d]">Open control room <Arrow /></a><a href="#workflow" className="inline-flex items-center gap-2 rounded-full border border-black/10 bg-white px-5 py-3 text-sm font-semibold text-[#161916] transition hover:border-black/30">See the workflow</a></div>
        </div>

        <div className="hero-visual relative mx-auto h-[480px] w-[min(86vw,460px)] lg:h-[calc(100svh-180px)] lg:min-h-[530px] lg:w-[460px]">
          <div className="absolute inset-0 rounded-[30px] border border-[#1b241d] bg-[#121512] shadow-[0_30px_80px_rgba(15,25,17,0.2)]" />
          <div className="absolute inset-[1px] overflow-hidden rounded-[29px] bg-[radial-gradient(circle_at_55%_15%,rgba(56,216,107,0.32),transparent_26%),radial-gradient(circle_at_20%_90%,rgba(42,191,101,0.19),transparent_30%),#121512]">
            <div className="absolute inset-0 opacity-30 [background-image:radial-gradient(rgba(148,255,183,0.8)_1px,transparent_1px)] [background-size:16px_16px]" />
            <div className="relative flex h-full flex-col p-5 text-white sm:p-7">
              <div className="flex items-center justify-between border-b border-white/10 pb-4 text-[11px] font-medium tracking-[0.08em] text-white/55"><span>SOLO LICENSE / LIVE RUN</span><span className="flex items-center gap-2 text-[#79ee9e]"><i className="h-1.5 w-1.5 rounded-full bg-current" />VERIFIED</span></div>
              <div className="mt-9 rounded-2xl border border-[#5de98c]/30 bg-[#1b261d]/90 p-5 shadow-[0_0_34px_rgba(68,221,112,0.11)]">
                <p className="text-[11px] font-medium uppercase tracking-[0.14em] text-[#8bf2aa]">Refund authorization</p>
                <div className="mt-5 flex items-end justify-between"><div><p className="font-display text-4xl font-semibold tracking-[-0.07em]">L2</p><p className="mt-1 text-sm text-white/55">under ceiling</p></div><span className="rounded-full bg-[#2cbf65] px-3 py-1.5 text-xs font-bold text-[#0d180f]">Ready to act</span></div>
              </div>
              <div className="relative mt-auto grid grid-cols-4 gap-2"><div className="absolute left-[12%] right-[12%] top-[17px] h-px bg-[#62ed91]/60" />{['L0', 'L1', 'L2', 'L3'].map((level, index) => <div key={level} className="relative z-10"><span className={`grid h-9 w-9 place-items-center rounded-full border text-xs font-bold ${index === 2 ? 'border-[#75ee9d] bg-[#2cbf65] text-[#0b160e]' : 'border-white/20 bg-[#191d19] text-white/55'}`}>{level}</span><p className="mt-3 text-[10px] text-white/45">{['Suggest', 'Approve', 'Execute', 'Audit'][index]}</p></div>)}</div>
            </div>
          </div>
          <div className="hero-float absolute -right-3 top-[22%] rounded-xl border border-black/5 bg-white px-3 py-2.5 text-[12px] font-semibold text-[#161916] shadow-[0_14px_30px_rgba(16,22,17,0.16)]"><span className="mr-2 inline-block h-2 w-2 rounded-full bg-[#2cbf65]" />State verified</div>
          <div className="hero-float-delayed absolute -left-5 bottom-[18%] rounded-xl border border-white/10 bg-[#1a1e1a] px-3 py-2.5 text-[12px] font-semibold text-white shadow-[0_14px_30px_rgba(16,22,17,0.2)]">Detection <span className="ml-2 text-[#7cec9c]">clear</span></div>
        </div>

        <div className="hero-proof max-w-[300px] self-center justify-self-end lg:pb-12">
          <div className="hero-float inline-flex items-center gap-2 rounded-xl bg-white px-3.5 py-2.5 text-[13px] font-semibold shadow-[0_12px_28px_rgba(16,22,17,0.12)]"><span className="h-2 w-2 rounded-full bg-[#2cbf65] ring-4 ring-[#e5f8eb]" /> Solo License</div>
          <h2 className="mt-5 max-w-[8ch] font-display text-[clamp(2rem,3.15vw,3.35rem)] font-semibold leading-[0.93] tracking-[-0.075em]">Autonomy that stays inside its authority.</h2>
          <p className="mt-5 text-[15px] leading-6 text-neutral-500">The system verifies every side effect, records the evidence, and demotes on detection.</p>
        </div>
      </div>
    </section>

    <section id="workflow" className="border-y border-black/[0.08] bg-white px-7 py-24 md:px-12 md:py-32">
      <div className="section-reveal mx-auto max-w-[1280px]"><p className="text-xs font-semibold uppercase tracking-[0.16em] text-[#29b85d]">Verified workflow</p><div className="mt-6 grid gap-12 lg:grid-cols-[0.82fr_1.18fr]"><h2 className="max-w-[9ch] font-display text-[clamp(2.7rem,4.5vw,5rem)] font-semibold leading-[0.92] tracking-[-0.075em]">Permission is earned through proof.</h2><div className="grid border-t border-black/10 sm:grid-cols-3"><article className="border-b border-black/10 py-7 sm:border-b-0 sm:border-r sm:px-7"><span className="text-sm text-[#29b85d]">01</span><h3 className="mt-12 font-display text-xl font-semibold tracking-[-0.05em]">Check authority</h3><p className="mt-3 text-sm leading-6 text-neutral-500">Read the current license before a worker plans anything.</p></article><article className="border-b border-black/10 py-7 sm:border-b-0 sm:border-r sm:px-7"><span className="text-sm text-[#29b85d]">02</span><h3 className="mt-12 font-display text-xl font-semibold tracking-[-0.05em]">Execute or suggest</h3><p className="mt-3 text-sm leading-6 text-neutral-500">Do only what the task level authorises for that refund.</p></article><article className="py-7 sm:px-7"><span className="text-sm text-[#29b85d]">03</span><h3 className="mt-12 font-display text-xl font-semibold tracking-[-0.05em]">Verify state</h3><p className="mt-3 text-sm leading-6 text-neutral-500">Read SQLite back and attach the result to one packet.</p></article></div></div></div>
    </section>

    <section id="autonomy" className="bg-[#151815] px-7 py-24 text-white md:px-12 md:py-32"><div className="mx-auto grid max-w-[1280px] gap-12 lg:grid-cols-[0.8fr_1.2fr]"><div><p className="text-xs font-semibold uppercase tracking-[0.16em] text-[#67e695]">The autonomy ladder</p><h2 className="mt-6 max-w-[8ch] font-display text-[clamp(2.7rem,4.5vw,5rem)] font-semibold leading-[0.92] tracking-[-0.075em]">Four levels. One source of truth.</h2></div><div className="grid gap-2 sm:grid-cols-2"><div className="rounded-lg border border-white/15 bg-white/[0.05] p-7"><span className="text-sm text-[#67e695]">L0</span><h3 className="mt-12 font-display text-2xl font-semibold tracking-[-0.05em]">Suggest only</h3><p className="mt-3 text-sm leading-6 text-white/55">The worker explains what it would do. A human acts.</p></div><div className="rounded-lg border border-white/15 bg-white/[0.05] p-7"><span className="text-sm text-[#67e695]">L1</span><h3 className="mt-12 font-display text-2xl font-semibold tracking-[-0.05em]">Draft + approve</h3><p className="mt-3 text-sm leading-6 text-white/55">The worker prepares the execution for review.</p></div><div className="rounded-lg border border-white/15 bg-white/[0.05] p-7"><span className="text-sm text-[#67e695]">L2</span><h3 className="mt-12 font-display text-2xl font-semibold tracking-[-0.05em]">Under ceiling</h3><p className="mt-3 text-sm leading-6 text-white/55">Verified automatic refunds stay under a defined amount.</p></div><div className="rounded-lg border border-[#67e695]/50 bg-[#2cbf65] p-7 text-[#111510]"><span className="text-sm font-semibold">L3</span><h3 className="mt-12 font-display text-2xl font-semibold tracking-[-0.05em]">Full auto, audited</h3><p className="mt-3 text-sm leading-6 text-[#111510]/70">Authority remains earned and revocable, never assumed.</p></div></div></div></section>

    <section id="evidence" className="bg-[#f4f8f4] px-7 py-24 md:px-12 md:py-32"><div className="section-reveal mx-auto grid max-w-[1280px] items-end gap-10 lg:grid-cols-[1fr_0.9fr]"><div><p className="text-xs font-semibold uppercase tracking-[0.16em] text-[#29b85d]">Evidence packet</p><h2 className="mt-6 max-w-[10ch] font-display text-[clamp(2.7rem,4.5vw,5rem)] font-semibold leading-[0.92] tracking-[-0.075em]">One detection. One readable recovery path.</h2></div><div className="rounded-lg bg-white p-7 shadow-[0_24px_55px_rgba(16,22,17,0.09)]"><div className="flex items-center justify-between border-b border-black/10 pb-5 text-sm"><span className="font-semibold">Refund packet</span><span className="text-[#29b85d]">Verified</span></div><div className="grid grid-cols-3 border-b border-black/10 py-7 text-sm"><div><p className="text-neutral-500">Before</p><strong className="mt-2 block text-lg">$0.00</strong></div><div><p className="text-neutral-500">After</p><strong className="mt-2 block text-lg">$120.00</strong></div><div><p className="text-neutral-500">Intended</p><strong className="mt-2 block text-lg">$120.00</strong></div></div><p className="pt-5 text-sm leading-6 text-neutral-600">The packet holds the detection, trace, before/after state, and the human restoration decision.</p></div></div></section>

    <footer className="bg-[#151815] px-7 pb-8 pt-16 text-white md:px-12 md:pt-20"><div className="mx-auto max-w-[1280px]"><div className="grid gap-12 border-b border-white/15 pb-14 md:grid-cols-[1.2fr_0.8fr_0.75fr]"><div><a href="/landing" className="flex items-center gap-2.5 font-display text-lg font-semibold tracking-[-0.04em]"><Mark /> Solo License</a><p className="mt-5 max-w-[30ch] text-sm leading-6 text-white/55">Autonomy that stays inside its authority.</p></div><div className="flex flex-col gap-3 text-sm"><a className="text-white/65 transition hover:text-[#79ee9e]" href="#workflow">How it works</a><a className="text-white/65 transition hover:text-[#79ee9e]" href="#autonomy">Autonomy</a><a className="text-white/65 transition hover:text-[#79ee9e]" href="#evidence">Evidence</a></div><div className="md:justify-self-end"><p className="text-sm text-white/55">Ready when the evidence is.</p><a href="/" className="mt-4 inline-flex items-center gap-2 rounded-full bg-[#2cbf65] px-4 py-2.5 text-sm font-semibold text-[#101810] transition hover:bg-[#79ee9e]">Open product <Arrow /></a></div></div><div className="flex flex-wrap justify-between gap-4 pt-7 text-xs text-white/40"><span>Solo License</span><span>Earned autonomy for refund operations.</span></div></div></footer>
  </main>;
}
