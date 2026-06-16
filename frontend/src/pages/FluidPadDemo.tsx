import { FluidEmotionPad, FLUID_PAD_WRAPPER_PX } from "../components/FluidEmotionPad";

export default function FluidPadDemo() {
  return (
    <div
      className="mx-auto flex min-h-screen flex-col gap-8 p-6"
      style={{ maxWidth: FLUID_PAD_WRAPPER_PX + 48 }}
    >
      <header>
        <a
          href="/"
          className="mb-4 inline-block text-sm text-white/40 transition hover:text-white/70"
        >
          ← Back to Moony
        </a>
        <h1 className="text-2xl font-semibold tracking-tight">Fluid Pad — Demo</h1>
        <p className="text-sm text-white/50">
          Prototype circular control with WebGL fluid animation and a dotted-sphere pointer.
        </p>
        <p className="mt-1 text-xs text-white/30">
          Drag or hold the pointer — fluid emits continuously.
        </p>
      </header>

      <section className="mx-auto flex flex-col items-center gap-6">
        <FluidEmotionPad onPositionChange={() => {}} />

        <div className="max-w-md rounded-xl border border-white/10 bg-white/[0.03] px-4 py-3 text-center text-xs leading-relaxed text-white/40">
          Fluid animation based on{" "}
          <a
            href="https://codepen.io/RunicFreak/pen/abKPYJa"
            target="_blank"
            rel="noreferrer"
            className="text-moony-glow/80 underline-offset-2 hover:underline"
          >
            WebGL Fluid Animation
          </a>{" "}
          by RunicFreak, contained in the circle with a convex dotted-sphere pointer.
        </div>
      </section>
    </div>
  );
}
