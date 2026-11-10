// Run with `npm test` (node:test, no dependencies).
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { consoleEvent } from './consoleEvents.js'

const VANILLA = '[12:00:00] [Server thread/INFO]: '
const PAPER = '[12:00:00 INFO]: '
const NEOFORGE = '[10Nov2026 12:00:00.123] [Server thread/INFO] [net.minecraft.server.MinecraftServer/]: '

test('recognises each event after every log prefix', () => {
  for (const prefix of [VANILLA, PAPER, NEOFORGE]) {
    assert.equal(consoleEvent(`${prefix}<Steve> hi there`), 'CHAT')
    assert.equal(consoleEvent(`${prefix}Steve joined the game`), 'JOIN')
    assert.equal(consoleEvent(`${prefix}Steve has made the advancement [Stone Age]`), 'ADVANCEMENT')
    assert.equal(consoleEvent(`${prefix}Steve was slain by Zombie`), 'DEATH')
  }
})

test('chat variants', () => {
  for (const body of [
    '[Not Secure] <Steve> hi',
    '<[Red] Steve> team colours sit inside the brackets',
    '* Steve waves',
    '[Server] restart in 5 minutes',
    '[Rcon] backup done'
  ]) {
    assert.equal(consoleEvent(VANILLA + body), 'CHAT', body)
  }
})

test('joins, leaves, achievements and old and new death wordings', () => {
  const cases = {
    'Steve left the game': 'JOIN',
    '.Bedrock Player joined the game': 'JOIN',
    'Steve has completed the challenge [Monsters Hunted]': 'ADVANCEMENT',
    'Steve has reached the goal [Sky\'s the Limit]': 'ADVANCEMENT',
    'Steve has just earned the achievement [Taking Inventory]': 'ADVANCEMENT',
    'Steve drowned': 'DEATH',
    'Steve died': 'DEATH',
    'Steve fell off a ladder': 'DEATH',
    'Steve hit the ground too hard whilst trying to escape Creeper': 'DEATH',
    'Steve was blown up by Creeper': 'DEATH',
    'Steve was knocked into the void by Enderman': 'DEATH',
    'Steve froze to death': 'DEATH',
    'Steve experienced kinetic energy': 'DEATH',
    "Steve didn't want to live in the same world as Alex": 'DEATH'
  }
  for (const [body, event] of Object.entries(cases)) {
    assert.equal(consoleEvent(VANILLA + body), event, body)
  }
})

test('26.3 "System chat:" marker', () => {
  assert.equal(consoleEvent(`${VANILLA}System chat: Steve joined the game`), 'JOIN')
  assert.equal(consoleEvent(`${VANILLA}System chat: Steve was slain by Zombie`), 'DEATH')
})

test('ANSI colour codes are ignored', () => {
  assert.equal(consoleEvent(`${PAPER}\x1b[33mSteve joined the game\x1b[0m`), 'JOIN')
})

test('a player cannot fake an event through chat', () => {
  assert.equal(consoleEvent(`${VANILLA}<Steve> Alex joined the game`), 'CHAT')
  assert.equal(consoleEvent(`${VANILLA}<Steve> Alex was slain by Zombie`), 'CHAT')
})

test('ordinary log lines are no event', () => {
  for (const line of [
    `${VANILLA}Starting minecraft server version 1.21.1`,
    `${VANILLA}Done (4.123s)! For help, type "help"`,
    `${VANILLA}Steve lost connection: Disconnected`,
    `${VANILLA}Steve[/127.0.0.1:52344] logged in with entity id 123 at (0.5, 64.0, 0.5)`,
    `${VANILLA}Named entity Wolf['Fido'/42, l='ServerLevel[world]'] died: Fido was slain by Zombie`,
    `${VANILLA}[Botania] Loaded 120 recipes`,
    '[12:00:00] [Server thread/WARN]: Steve moved too quickly!',
    'Steve joined the game',
    '<Steve> hi'
  ]) {
    assert.equal(consoleEvent(line), null, line)
  }
})
