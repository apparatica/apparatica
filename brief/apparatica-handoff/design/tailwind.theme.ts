// Apparatica · Bench — тема Tailwind. Цвета читаются из CSS-переменных (tokens.css), поэтому тёмная тема включается атрибутом data-theme.
// Использование: bg-sf text-mu border-bc  |  bg-ac text-acx  |  bg-oks text-ok  |  text-kw
import type { Config } from 'tailwindcss';

const v = (name: string) => `var(--${name})`;
const names = ['bg', 'sf', 'sf2', 'ed', 'bd', 'bc', 'tx', 'mu', 'ac', 'acx', 'acs', 'ok', 'oks', 'er', 'ers', 'wn', 'wns', 'in', 'ins', 'e', 'es', 'm', 'ms', 'h', 'hs', 'h1', 'h2', 'h3', 'h4', 'kw', 'ty', 'nm', 'cm', 'fn'] as const;
const colors = Object.fromEntries(names.map((n) => [n, v(n)]));

export default {
  theme: {
    extend: {
      colors,
      fontFamily: { sans: ['var(--sans)'], mono: ['var(--mono)'] },
      borderRadius: { sm: '2px', DEFAULT: '3px', md: '3px', lg: '4px' },
      fontSize: {
        display: ['34px', { lineHeight: '42px', fontWeight: '600', letterSpacing: '-0.02em' }],
        h1: ['22px', { lineHeight: '30px', fontWeight: '600', letterSpacing: '-0.01em' }],
        h2: ['17px', { lineHeight: '26px', fontWeight: '600' }],
        statement: ['13.5px', '22px'],
        body: ['13px', '20px'],
        caption: ['12px', '17px'],
        label: ['10.5px', { lineHeight: '14px', letterSpacing: '0.08em' }],
        code: ['12.5px', '19px'],
        metric: ['26px', { lineHeight: '34px', fontWeight: '500', letterSpacing: '-0.02em' }],
      },
      spacing: { 1: '4px', 2: '8px', 3: '12px', 4: '16px', 5: '20px', 6: '24px', 8: '32px' },
      boxShadow: { window: '0 16px 48px var(--sh)', pop: '0 8px 24px var(--sh)' },
    },
  },
} satisfies Partial<Config>;
