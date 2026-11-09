/**
 * Built-in JVM flag presets (#108), listed next to the user's own saved ones in
 * a server's Java settings. `hint` is an i18n key. `minJava`/`maxJava` bound the
 * Java versions the flags start on cleanly (checked on Temurin 8, 11, 17 and
 * 21–25); the page disables a preset outside them.
 *
 * No -Xms/-Xmx: the heap comes from the Memory setting, and the backend refuses
 * heap flags in JVM arguments.
 */

// mcflags.emc.gs, in its order. The 12 GB+ variant only changes the sizing values.
const aikar = (newSize, maxNewSize, regionSize, reserve, occupancy) =>
  [
    '-XX:+UseG1GC',
    '-XX:+ParallelRefProcEnabled',
    '-XX:MaxGCPauseMillis=200',
    '-XX:+UnlockExperimentalVMOptions',
    '-XX:+DisableExplicitGC',
    '-XX:+AlwaysPreTouch',
    `-XX:G1NewSizePercent=${newSize}`,
    `-XX:G1MaxNewSizePercent=${maxNewSize}`,
    `-XX:G1HeapRegionSize=${regionSize}`,
    `-XX:G1ReservePercent=${reserve}`,
    '-XX:G1HeapWastePercent=5',
    '-XX:G1MixedGCCountTarget=4',
    `-XX:InitiatingHeapOccupancyPercent=${occupancy}`,
    '-XX:G1MixedGCLiveThresholdPercent=90',
    '-XX:G1RSetUpdatingPauseTimePercent=5',
    '-XX:SurvivorRatio=32',
    '-XX:+PerfDisableSharedMem',
    '-XX:MaxTenuringThreshold=1',
    '-Dusing.aikars.flags=https://mcflags.emc.gs',
    '-Daikars.new.flags=true'
  ].join(' ')

export const BUILTIN_JVM_PRESETS = [
  {
    id: 'aikar',
    name: "Aikar's flags",
    hint: 'properties.java.presetHints.aikar',
    args: aikar(30, 40, '8M', 20, 15)
  },
  {
    id: 'aikar-12g',
    name: "Aikar's flags (12 GB+)",
    hint: 'properties.java.presetHints.aikar12g',
    args: aikar(40, 50, '16M', 15, 20)
  },
  {
    // Without ZGenerational, 21 and 22 run the legacy single-generation mode.
    // 17 rejects the option, 23 warns it is deprecated and 24+ that it is ignored.
    id: 'zgc-21',
    name: 'Generational ZGC (Java 21–22)',
    hint: 'properties.java.presetHints.zgc',
    minJava: 21,
    maxJava: 22,
    args: '-XX:+UseZGC -XX:+ZGenerational'
  },
  {
    id: 'zgc',
    name: 'Generational ZGC (Java 23+)',
    hint: 'properties.java.presetHints.zgc',
    minJava: 23,
    args: '-XX:+UseZGC'
  },
  {
    // Not in Temurin 8.
    id: 'shenandoah',
    name: 'Shenandoah (Java 11+)',
    hint: 'properties.java.presetHints.shenandoah',
    minJava: 11,
    args: '-XX:+UseShenandoahGC'
  }
]
