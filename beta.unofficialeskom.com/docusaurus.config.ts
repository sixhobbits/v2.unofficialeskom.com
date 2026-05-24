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

  // GitHub pages deployment config.
  // If you aren't using GitHub pages, you don't need these.
  organizationName: 'facebook', // Usually your GitHub org/user name.
  projectName: 'docusaurus', // Usually your repo name.

  onBrokenLinks: 'throw',

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
        docs: {
          sidebarPath: './sidebars.ts',
          // Please change this to your repo.
          // Remove this to remove the "edit this page" links.
          editUrl:
            'https://github.com/facebook/docusaurus/tree/main/packages/create-docusaurus/templates/shared/',
        },
        blog: {
          showReadingTime: true,
          feedOptions: {
            type: ['rss', 'atom'],
            xslt: true,
          },
          // Please change this to your repo.
          // Remove this to remove the "edit this page" links.
          editUrl:
            'https://github.com/facebook/docusaurus/tree/main/packages/create-docusaurus/templates/shared/',
          // Useful options to enforce blogging best practices
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
    image: 'img/docusaurus-social-card.jpg',
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
        {to: '/dashboard', label: 'Dashboard', position: 'left'},
      ],
    },
    footer: {
      style: 'dark',
      copyright: `Copyright © ${new Date().getFullYear()} <a href="https://dwyer.co.za" target="_blank" rel="noopener noreferrer">Gareth Dwyer</a>. Not endorsed by or affiliated with Eskom.`,
    },
    prism: {
      theme: prismThemes.github,
      darkTheme: prismThemes.dracula,
    },
  } satisfies Preset.ThemeConfig,
};

export default config;
