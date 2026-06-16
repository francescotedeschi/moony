/** Exponent for perceptual master volume (2 ≈ common “audio taper”). */
const PERCEPTUAL_EXPONENT = 2;

function clamp01(n: number): number {
  return Math.max(0, Math.min(1, n));
}

/** Slider / UI level (perceived loudness) → linear amplitude for HTMLAudioElement.volume */
export function perceptualToAmplitude(perceived: number): number {
  return Math.pow(clamp01(perceived), PERCEPTUAL_EXPONENT);
}

/** Linear amplitude → perceived level for slider display */
export function amplitudeToPerceptual(amplitude: number): number {
  const a = clamp01(amplitude);
  return Math.pow(a, 1 / PERCEPTUAL_EXPONENT);
}
