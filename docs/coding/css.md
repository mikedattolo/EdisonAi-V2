# CSS Reference

Styling for the web. Edison's styles live in `apps/web/src/styles.css` (class-based: `.creator-*`, `.code-agent-*`, `.message`, `.composer`, etc.) plus design tokens under `:root` (`--edison-accent`, `--edison-border`, `--edison-radius`, shadows).

## Selectors & specificity
- `.class`, `#id`, `element`, `*`, `[attr=value]`, descendant `.a .b`, child `.a > .b`, `:hover :focus :active :disabled :first-child :nth-child(2) :not(.x)`, `::before ::after`.
- Specificity: inline > id > class/attr/pseudo-class > element. Later rules win at equal specificity. Avoid `!important` except as a last resort.

## Box model & units
- `box-sizing: border-box` (width includes padding+border — set globally). `margin` (outside), `padding` (inside), `border`, `width/height`, `min-/max-`.
- Units: `px` fixed, `rem` (root font size, scalable — prefer for type/spacing), `em` (relative to element), `%`, `vh/vw`, `fr` (grid), `ch`.
- Colors: `#rrggbb`, `rgb()/rgba()`, `hsl()`, named. Use CSS variables: `color: var(--edison-accent)`.

## Layout
- Flexbox (1D): `display:flex; flex-direction:row|column; justify-content:space-between|center; align-items:center; gap:12px; flex:1 1 auto; flex-wrap:wrap;`.
- Grid (2D): `display:grid; grid-template-columns: 240px minmax(0,1fr); gap:16px; grid-template-rows:auto 1fr;`. Place items with `grid-column`.
- Position: `static` (default), `relative`, `absolute` (to nearest positioned ancestor), `fixed`, `sticky`. `top/right/bottom/left`, `z-index`.
- `display: none` removes; `visibility: hidden` keeps space. `overflow: auto|hidden|scroll`.

## Typography & visuals
- `font-family`, `font-size`, `font-weight`, `line-height` (~1.5–1.7 for body), `letter-spacing`, `text-align`, `text-transform`, `white-space: pre-wrap`, `word-break`.
- `border-radius`, `box-shadow: 0 1px 2px rgba(0,0,0,.05)`, `background`, `opacity`, `transition: all .15s ease`, `transform: translateY(-2px)`.

## Responsive
- Mobile-first: base styles, then `@media (max-width: 900px) { ... }` to adjust. Test single-column collapses.
- Use `minmax()`, `clamp(min, preferred, max)`, `width: min(100%, 920px)` for fluid sizing.

## Variables (custom properties)
```css
:root { --accent: #1f6f62; --radius: 14px; }
.button { background: var(--accent); border-radius: var(--radius); }
```
Change a token once → it updates everywhere it's used. Edison defines its palette/radii/shadows this way.

## Good practices
- Style with classes, not inline or id selectors; keep specificity low and flat.
- Reuse design tokens (`var(--edison-*)`) instead of hardcoding new colors so the UI stays consistent.
- Prefer fl/grid + `gap` over margins for spacing between items. Add `:focus-visible` styles for keyboard users.
- When editing this big stylesheet, change the existing rule for a class rather than adding duplicates; append new component rules at the end.
