# HTML Reference

Structure of a web page. Edison's UI is rendered by React, but the same elements/attributes apply in JSX (with `className` instead of `class`).

## Document skeleton
```html
<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Page title</title>
    <link rel="stylesheet" href="/styles.css" />
  </head>
  <body>
    <!-- content -->
    <script type="module" src="/main.js"></script>
  </body>
</html>
```

## Semantic structure (prefer these over generic divs)
- `<header> <nav> <main> <section> <article> <aside> <footer>` — page regions.
- Headings `<h1>`–`<h6>` (one `<h1>` per page, don't skip levels). `<p>` paragraph, `<ul>/<ol>/<li>` lists, `<figure>/<figcaption>`.
- Inline: `<a href="...">`, `<strong>` (importance), `<em>` (emphasis), `<span>`, `<code>`, `<small>`, `<time datetime="...">`.

## Links, media, tables
- `<a href="/path" target="_blank" rel="noreferrer">` (always add rel for target=_blank).
- `<img src="..." alt="describe the image" width height loading="lazy" />` — alt is required for accessibility.
- `<video controls>`, `<audio controls>`, `<source src>`. `<table><thead><tr><th></thead><tbody><tr><td></tbody></table>`.

## Forms & inputs
- `<form>` with `<label for="id">` + `<input id="id" name="..." type="text">`.
- Input types: `text email password number search url tel date file checkbox radio range color`.
- Controls: `<textarea rows>`, `<select><option value>`, `<button type="submit|button">`. Attributes: `required placeholder disabled readonly min max step pattern value`.
- Always pair a `<label>` with each control (click target + screen-reader name).

## Attributes worth knowing
- `id` (unique), `class` (styling hook; `className` in JSX), `data-*` (custom data), `title` (tooltip), `hidden`.
- Accessibility: `aria-label`, `aria-labelledby`, `aria-hidden`, `role="..."`, `tabindex`. Use semantic elements first; add ARIA only to fill gaps.

## Good practices
- One `<h1>`; logical heading order. Every image has `alt`; every input has a `<label>`.
- Use semantic tags so the page is navigable and accessible. Keep markup minimal; style with CSS, behave with JS.
- Validate forms with native attributes (`required`, `type`, `pattern`) before JS.
