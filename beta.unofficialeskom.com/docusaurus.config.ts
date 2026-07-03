import {themes as prismThemes} from 'prism-react-renderer';
import type {Config} from '@docusaurus/types';
import type * as Preset from '@docusaurus/preset-classic';

// This runs in Node.js - Don't use client-side code here (browser APIs, JSX...)

const config: Config = {
  title: 'Unofficial Eskom',
  tagline: 'Independent dashboards over South Africa\'s electricity supply',
  favicon: 'img/favicon.png',

  // Future flags, see https://docusaurus.io/docs/api/docusaurus-config#future
  future: {
    v4: true, // Improve compatibility with the upcoming Docusaurus v4
  },

  // Set the production url of your site here
  url: 'https://beta.unofficialeskom.com',
  // Set the /<baseUrl>/ pathname under which your site is served
  // For GitHub pages deployment, it is often '/<projectName>/'
  baseUrl: '/',

  organizationName: 'sixhobbits',
  projectName: 'v2.unofficialeskom.com',

  onBrokenLinks: 'throw',

  // Baked at build time; useDashboardData() appends it as ?v= to the
  // dashboard-data.json fetch so new JS never reuses a stale cached payload.
  customFields: {
    buildId: String(Date.now()),
  },

  // Seed the colorMode storage from prefers-color-scheme on first visit so
  // initial mode follows the OS even though respectPrefersColorScheme is off
  // (we disable that to get a binary light/dark toggle without a "system"
  // option). Runs synchronously in <head> before Docusaurus's own theme init.
  headTags: [
    {
      tagName: 'script',
      attributes: {},
      innerHTML:
        "try{var k='theme-d92';if(!localStorage.getItem(k)){var m=window.matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light';localStorage.setItem(k,m);localStorage.setItem('theme',m);}}catch(e){}",
    },
    // Privacy-friendly analytics by Plausible
    {
      tagName: 'script',
      attributes: {
        async: 'true',
        src: 'https://plausible.io/js/pa-3Zy4dHgOqFFz1Yc-yG7Qf.js',
      },
    },
    {
      tagName: 'script',
      attributes: {},
      innerHTML:
        "window.plausible=window.plausible||function(){(plausible.q=plausible.q||[]).push(arguments)},plausible.init=plausible.init||function(i){plausible.o=i||{}};plausible.init()",
    },
  ],

  // Even if you don't use internationalization, you can use this field to set
  // useful metadata like html lang. For example, if your site is Chinese, you
  // may want to replace "en" with "zh-Hans".
  i18n: {
    defaultLocale: 'en',
    locales: ['en'],
  },

  presets: [
    [
      'classic',
      {
        // No docs — the site is dashboard pages + the /updates blog.
        docs: false,
        blog: {
          // Route kept as /updates (published post URLs); the tab is "Analysis".
          routeBasePath: 'updates',
          blogTitle: 'Analysis',
          blogDescription: 'Monthly analysis of the unofficial Eskom data',
          blogSidebarTitle: 'All posts',
          blogSidebarCount: 'ALL',
          showReadingTime: true,
          feedOptions: {
            type: ['rss', 'atom'],
            xslt: true,
          },
          onInlineTags: 'warn',
          onInlineAuthors: 'warn',
          onUntruncatedBlogPosts: 'warn',
        },
        theme: {
          customCss: './src/css/custom.css',
        },
      } satisfies Preset.Options,
    ],
  ],

  themeConfig: {
    // Replace with your project's social card
    image: 'img/og-card.jpg',
    colorMode: {
      respectPrefersColorScheme: false,
    },
    navbar: {
      title: 'Unofficial Eskom',
      logo: {
        alt: 'Unofficial Eskom',
        src: 'img/logo.png',
      },
      items: [
        {to: '/', label: 'Home', position: 'left'},
        {to: '/status', label: 'Status', position: 'left'},
        {to: '/dashboard', label: 'Dashboard', position: 'left'},
        {to: '/monthly', label: 'Long term', position: 'left'},
        {to: '/heatmap', label: 'Heatmap', position: 'left'},
        {to: '/financials', label: 'Financials', position: 'left'},
        {to: '/updates', label: 'Analysis', position: 'left'},
        {to: '/eskom-source-data', label: 'Source data', position: 'left'},
      ],
    },
    footer: {
      style: 'dark',
      links: [
        {
          items: [
            {label: 'GitHub', href: 'https://github.com/sixhobbits/v2.unofficialeskom.com'},
            {label: 'Bluesky', href: 'https://bsky.app/profile/sixhobbits.bsky.social'},
            {label: 'Source data', to: '/eskom-source-data'},
          ],
        },
      ],
      copyright: `Copyright © ${new Date().getFullYear()} <a href="https://dwyer.co.za" target="_blank" rel="noopener noreferrer">Gareth Dwyer</a>. Not endorsed by or affiliated with Eskom.`,
    },
    prism: {
      theme: prismThemes.github,
      darkTheme: prismThemes.dracula,
    },
  } satisfies Preset.ThemeConfig,
};

export default config;
