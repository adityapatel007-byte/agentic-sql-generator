# Product

## Register

product

## Users

Developers, data analysts, and technical PMs poking at unfamiliar databases without writing SQL by hand — plus the author (a candidate for AI/ML roles) using the surface as a working portfolio piece a hiring manager can drive in 30 seconds. Both audiences are technically fluent; they will notice sloppy UX and reward considered UX.

## Product Purpose

Turn a plain-English question and a database (SQLite or Postgres) into a correct SQL query and an executed answer, using a small agentic loop with schema-aware RAG. The interface has to make the *reasoning* visible — every tool call, every retry, the final SQL — because that transparency is the whole pitch versus a black-box "AI SQL" widget. Success = a technical viewer trusts what they're seeing within one interaction.

## Brand Personality

Terminal-native, dev-first, quietly confident. The tool that a senior engineer would leave open in a workspace tab — not the tool that markets itself. Voice: precise, low, no exclamation marks. Feels closer to `psql` + Warp + Linear than to any consumer AI chat product.

## Anti-references

- **Generic ChatGPT wrapper.** Dark chat bubbles, purple accent, sidebar drawer, message list, "AI-generated look".
- **Scientist notebook / Streamlit.** Boxy cards, wide unstructured layout, utilitarian, no hierarchy.
- **Corporate SaaS dashboard.** Blue accent, sidebar nav with icons + labels, KPI-tile grid, default-Tailwind chrome.
- **Over-designed marketing page.** Giant hero, mesh gradients, animated blobs. Wrong register for a tool.
- **AI-slop landing.** Cream / warm-tinted body bg, eyebrow kickers on every section, 24px+ rounded cards, gradient text, tiny hand-drawn SVG doodles.

## Design Principles

1. **Show the work, don't hide it.** The agent's tool calls, retries, and final SQL are first-class content, not a debug panel. Users came to trust the reasoning; give them the reasoning.
2. **One committed color.** A single crushed-magenta accent carries "active", "cursor", "current iteration". Everything else is monochrome. No decorative color, ever.
3. **Mono-first.** One font family (Geist Mono) carries UI, labels, data, and code. Terminal-native means no display-serif moments, no font pairing.
4. **Sharp, not rounded.** 2-8px radii. Hairline borders instead of drop-shadows. Sharp signals precision; blob signals playroom.
5. **Keyboard reachable.** Every primary action has a key. Visible hints in a status bar, not tucked in menus. Fluent users should never need the mouse.
6. **Density earned, not decorated.** Show more per screen when the user is in a task, but every element has to earn its space. No empty cards, no decorative dividers, no ambient stats.

## Accessibility & Inclusion

- Target WCAG 2.2 AA.
  - Body text ≥ 4.5:1 vs its surface. The mono palette is designed against this: ink at OKLCH 0.96 on bg 0.13 hits ~14:1; muted at 0.62 hits ~5.5:1.
  - Focus rings are always visible (2px, accent color at full L).
- `prefers-reduced-motion: reduce` disables cursor blink and any non-essential transition; state changes fall back to instant.
- Full keyboard operability: no functionality mouse-only.
- Colorblind consideration: accent (magenta) and success (desaturated green) are used with icons + text labels, never color alone. Error states carry copy.
- Screen-reader labels on all icon-only buttons.
- System dark-mode respected; light-mode is a competent mirror, not a second-class alternate.
