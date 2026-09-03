// @ts-check
import fs from 'node:fs';
import path from 'node:path';
import { defineConfig } from 'astro/config';
import starlight from '@astrojs/starlight';

// For a GitHub Pages *project* site the base must be the repo name, e.g.
//   SITE=https://you.github.io BASE=/empyrean-wiki npm run build
// For a user/org site or a custom domain, leave BASE unset.
const SITE = process.env.SITE || 'https://example.github.io';
const BASE = process.env.BASE || '/';

// Beta mode: NOINDEX=1 asks search engines to stay away, so the site is
// reachable by anyone with the link but does not turn up in search results.
// This is not access control — see the README before treating it as private.
const NOINDEX = ['1', 'true', 'yes'].includes(String(process.env.NOINDEX).toLowerCase());

/** Writes a disallow-everything robots.txt after the build, in beta mode. */
function robotsTxt() {
  return {
    name: 'wiki-robots-txt',
    hooks: {
      'astro:build:done': ({ dir }) => {
        const body = NOINDEX
          ? 'User-agent: *\nDisallow: /\n'
          : `User-agent: *\nAllow: /\nSitemap: ${new URL(
              path.posix.join(BASE, 'sitemap-index.xml'),
              SITE,
            ).href}\n`;
        fs.writeFileSync(path.join(new URL(dir).pathname.replace(/^\/(\w:)/, '$1'),
                                   'robots.txt'), body);
      },
    },
  };
}

export default defineConfig({
  site: SITE,
  base: BASE,
  trailingSlash: 'ignore',
  integrations: [
    starlight({
      title: 'Pokémon Empyrean Wiki',
      description:
        'Community wiki for Pokémon Empyrean — Pokédex, moves, abilities, items and type chart, generated directly from the game files.',
      favicon: '/favicon.png',
      customCss: ['./src/styles/wiki.css'],
      pagination: false,
      lastUpdated: false,
      head: NOINDEX
        ? [{ tag: 'meta', attrs: { name: 'robots', content: 'noindex, nofollow' } }]
        : [],
      sidebar: [
        { label: 'Pokédex', link: '/pokedex/' },
        { label: 'Moves', link: '/moves/' },
        { label: 'Abilities', link: '/abilities/' },
        { label: 'Items', link: '/items/' },
        { label: 'Cards', link: '/cards/' },
        { label: 'Locations', link: '/locations/' },
        { label: 'Gyms & badges', link: '/gyms/' },
        { label: 'Bosses', link: '/bosses/' },
        { label: 'Trainers', link: '/trainers/' },
        { label: 'Type chart', link: '/types/' },
        { label: 'About this wiki', link: '/about/' },
      ],
    }),
    robotsTxt(),
  ],
});
