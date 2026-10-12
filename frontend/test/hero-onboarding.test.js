import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

const heroPath = fileURLToPath(new URL('../src/features/landing/sections/Hero.jsx', import.meta.url));
const askBarPath = fileURLToPath(new URL('../src/features/landing/sections/AskBar.jsx', import.meta.url));

test('hero centers one onboarding command without the gate-feed visual', async () => {
  const [hero, askBar] = await Promise.all([
    readFile(heroPath, 'utf8'),
    readFile(askBarPath, 'utf8'),
  ]);

  assert.match(hero, /<AskBar\s*\/>/);
  assert.match(askBar, /solo-license onboard/);
  assert.doesNotMatch(hero, /HeroGateFeed/);
  assert.doesNotMatch(hero, /lp-hero-visual/);
  assert.doesNotMatch(hero, /lp-hero-meta/);
});
