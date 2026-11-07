/**
 * Built-in JVM flag presets (#108), listed next to the user's own saved ones in
 * a server's Java settings. `hint` is an i18n key.
 *
 * No -Xms/-Xmx: the heap comes from the Memory setting, and the backend refuses
 * heap flags in JVM arguments.
 */
export const BUILTIN_JVM_PRESETS = [
  {
    id: 'aikar',
    name: "Aikar's flags",
    hint: 'properties.java.presetHints.aikar',
    // docs.papermc.io/paper/aikars-flags, in the page's order.
    args: [
      '-XX:+UseG1GC',
      '-XX:+ParallelRefProcEnabled',
      '-XX:MaxGCPauseMillis=200',
      '-XX:+UnlockExperimentalVMOptions',
      '-XX:+DisableExplicitGC',
      '-XX:+AlwaysPreTouch',
      '-XX:G1NewSizePercent=30',
      '-XX:G1MaxNewSizePercent=40',
      '-XX:G1HeapRegionSize=8M',
      '-XX:G1ReservePercent=20',
      '-XX:G1HeapWastePercent=5',
      '-XX:G1MixedGCCountTarget=4',
      '-XX:InitiatingHeapOccupancyPercent=15',
      '-XX:G1MixedGCLiveThresholdPercent=90',
      '-XX:G1RSetUpdatingPauseTimePercent=5',
      '-XX:SurvivorRatio=32',
      '-XX:+PerfDisableSharedMem',
      '-XX:MaxTenuringThreshold=1',
      '-Dusing.aikars.flags=https://mcflags.emc.gs',
      '-Daikars.new.flags=true'
    ].join(' ')
  }
]
