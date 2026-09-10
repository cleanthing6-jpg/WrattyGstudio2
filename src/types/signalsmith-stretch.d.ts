declare module "signalsmith-stretch" {
  const SignalsmithStretch: (
    context: BaseAudioContext,
    options?: AudioWorkletNodeOptions
  ) => Promise<AudioNode>;
  export default SignalsmithStretch;
}
