/**
 * Display names of the built-in color themes.
 *
 * Every entry is a proper noun: a palette another project named (Dracula, Nord,
 * Gruvbox, Everforest), a product (IntelliJ), or the display technology it is
 * tuned for (AMOLED). Translating one would sever the name from the palette a
 * user is looking for, so they stay verbatim, and live here so the i18n
 * exemption in `eslint.i18n.config.js` covers this one file instead of the
 * theme registry. Same pattern as `fontFamilyOptions.ts`.
 *
 * `highcontrast` is the fallback for the one descriptive name; its translated
 * display string is `hooks.theme.high_contrast`.
 */
export const BUILTIN_THEME_NAME = {
  emerald: 'Emerald',
  monokai: 'Monokai',
  solarized: 'Solarized',
  amber: 'Amber',
  dracula: 'Dracula',
  nord: 'Nord',
  rosepine: 'Rosé Pine',
  catppuccin: 'Catppuccin',
  tokyonight: 'Tokyo Night',
  gruvbox: 'Gruvbox',
  ice: 'Ice',
  amoled: 'AMOLED',
  intellij: 'IntelliJ',
  highcontrast: 'High Contrast',
  everforest: 'Everforest',
  amoledMidnight: 'AMOLED Midnight',
  amoledGreyCalm: 'AMOLED Grey Calm',
} as const
