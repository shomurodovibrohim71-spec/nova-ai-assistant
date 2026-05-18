"""
design_feature.py — Telegram bot design generation feature.

Flow:
  /style  →  inline style keyboard
          →  inline platform keyboard
          →  user sends topic text
          →  Claude generates SVG
          →  PNG sent with caption

Register in your bot:
    from design_feature import register_design_handlers
    register_design_handlers(application)
"""
from __future__ import annotations

import asyncio
import logging
import tempfile
from pathlib import Path

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

log = logging.getLogger(__name__)

# ── Platform config ────────────────────────────────────────────────────────────

PLATFORM_SIZES: dict[str, tuple[int, int]] = {
    "instagram_post":  (1080, 1080),
    "instagram_story": (1080, 1920),
    "telegram_post":   (1280, 720),
    "universal":       (1080, 1080),
}

PLATFORM_META: dict[str, dict] = {
    "instagram_post": {
        "label": "Instagram Post",
        "emoji": "📸",
        "prompt": (
            "Canvas: 1080x1080. Square layout. Main content centered. "
            "Safe zone: keep all text within 900x900 center area."
        ),
    },
    "instagram_story": {
        "label": "Instagram Story",
        "emoji": "📱",
        "prompt": (
            "Canvas: 1080x1920. Vertical layout. Top 1/3: visual/headline, "
            "middle 1/3: main content, bottom 1/3: CTA or details. "
            "Keep text within x=80 to x=1000."
        ),
    },
    "telegram_post": {
        "label": "Telegram Post",
        "emoji": "✈️",
        "prompt": (
            "Canvas: 1280x720. Horizontal/landscape layout. "
            "Left side: main headline and key info. "
            "Right side: visual elements or supporting text. "
            "Keep text within safe margins."
        ),
    },
    "universal": {
        "label": "Universal Square",
        "emoji": "🖼️",
        "prompt": "Canvas: 1080x1080. Balanced square layout. Centered composition.",
    },
}

# ── Style config ───────────────────────────────────────────────────────────────

STYLE_META: dict[str, dict] = {
    "dark_luxury": {
        "label": "Dark Luxury",
        "emoji": "🖤",
        "prompt": (
            "Style: dark luxury. Deep black/charcoal background (#0A0A0A or #1A1A2E). "
            "Gold (#D4AF37) or platinum (#E5E4E2) accents. Elegant serif or thin sans-serif fonts. "
            "Minimalist layout with generous whitespace. Subtle geometric decorations."
        ),
    },
    "modern_gradient": {
        "label": "Modern Gradient",
        "emoji": "🌈",
        "prompt": (
            "Style: modern gradient. Bold gradient background (purple #6B48FF to pink #FF6B9D, "
            "or blue #0066FF to cyan #00D4FF). White text. Clean sans-serif font. "
            "Dynamic geometric shapes. High energy, eye-catching."
        ),
    },
    "clean_minimal": {
        "label": "Clean Minimal",
        "emoji": "⬜",
        "prompt": (
            "Style: clean minimal. White or very light grey background. Dark charcoal text (#1A1A1A). "
            "Single accent color (coral #FF6B6B or teal #4ECDC4). Lots of whitespace. "
            "Simple sans-serif font. No decorations, pure typography-driven."
        ),
    },
    "neon_cyber": {
        "label": "Neon Cyber",
        "emoji": "⚡",
        "prompt": (
            "Style: neon cyberpunk. Dark background (#050510). "
            "Neon glow effects: cyan (#00FFFF), hot pink (#FF00FF), electric green (#00FF41). "
            "Futuristic sans-serif or monospace font. Glitch-inspired decorative lines. "
            "High contrast, electric feel."
        ),
    },
    "corporate_pro": {
        "label": "Corporate Pro",
        "emoji": "💼",
        "prompt": (
            "Style: corporate professional. Navy blue (#003366) or deep teal (#006666) primary. "
            "White text, light grey secondary text. Clean grid layout. "
            "Subtle shadow/depth. Trust-inspiring, authoritative appearance."
        ),
    },
    "warm_organic": {
        "label": "Warm Organic",
        "emoji": "🌿",
        "prompt": (
            "Style: warm organic. Earthy warm tones: cream (#FFF8F0), terracotta (#C0614A), "
            "sage green (#7D9B76), warm beige (#D4B896). Rounded organic shapes. "
            "Friendly rounded sans-serif font. Natural, cozy, approachable feel."
        ),
    },
}

# ── SVG → PNG via Playwright ───────────────────────────────────────────────────

def svg_to_png(svg_code: str, width: int, height: int) -> bytes:
    """Wrap SVG in HTML, render with Playwright headless Chromium, return PNG bytes."""
    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  html, body {{ width: {width}px; height: {height}px; overflow: hidden; background: transparent; }}
  svg {{ display: block; width: {width}px; height: {height}px; }}
</style>
</head>
<body>{svg_code}</body>
</html>"""

    async def _render() -> bytes:
        from playwright.async_api import async_playwright
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
            page = await browser.new_page(viewport={"width": width, "height": height})
            await page.set_content(html, wait_until="domcontentloaded")
            await page.wait_for_timeout(800)
            png = await page.screenshot(
                clip={"x": 0, "y": 0, "width": width, "height": height},
                full_page=False,
            )
            await browser.close()
        return png

    return asyncio.get_event_loop().run_until_complete(_render())


# ── Claude SVG generation ──────────────────────────────────────────────────────

def _generate_svg_with_claude(
    topic: str,
    style_key: str,
    platform_key: str,
) -> str:
    import anthropic
    import os, re

    api_key = os.getenv("ANTHROPIC_API_KEY") or ""
    client = anthropic.Anthropic(api_key=api_key)

    style = STYLE_META[style_key]
    platform = PLATFORM_META[platform_key]
    w, h = PLATFORM_SIZES[platform_key]

    system_prompt = f"""You are a professional graphic designer creating social media post designs as SVG.

{style['prompt']}

{platform['prompt']}

Rules:
- Return ONLY valid SVG code starting with <svg ...> — no markdown, no explanation
- SVG viewBox must be "0 0 {w} {h}" and width="{w}" height="{h}"
- All fonts must be embedded or use system fonts (Arial, Helvetica, Georgia)
- No external image references
- Use <defs> for gradients, filters, clip-paths
- Text must have high contrast against background
- Make it look like a premium professional social media post"""

    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        system=system_prompt,
        messages=[{"role": "user", "content": f"Create a design for: {topic}"}],
    )

    raw = msg.content[0].text.strip()
    raw = re.sub(r"^```[a-z]*\n?", "", raw)
    raw = re.sub(r"\n?```$", "", raw)
    if not raw.startswith("<svg"):
        start = raw.find("<svg")
        if start != -1:
            raw = raw[start:]
    return raw


# ── Keyboards ──────────────────────────────────────────────────────────────────

def _style_keyboard() -> InlineKeyboardMarkup:
    keys = list(STYLE_META.items())
    rows = []
    for i in range(0, len(keys), 2):
        row = []
        for key, meta in keys[i : i + 2]:
            row.append(InlineKeyboardButton(
                f"{meta['emoji']} {meta['label']}",
                callback_data=f"design_style:{key}",
            ))
        rows.append(row)
    return InlineKeyboardMarkup(rows)


def _platform_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📸 Instagram Post",    callback_data="design_platform:instagram_post"),
            InlineKeyboardButton("📱 Instagram Story",   callback_data="design_platform:instagram_story"),
        ],
        [
            InlineKeyboardButton("✈️ Telegram Post",     callback_data="design_platform:telegram_post"),
            InlineKeyboardButton("🖼️ Universal Square",  callback_data="design_platform:universal"),
        ],
    ])


# ── Handlers ───────────────────────────────────────────────────────────────────

async def cmd_style(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Entry point: /style"""
    context.user_data.pop("design_style", None)
    context.user_data.pop("design_platform", None)
    await update.message.reply_text(
        "🎨 Choose a style for your design:",
        reply_markup=_style_keyboard(),
    )


async def cb_style(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """User picked a style → ask for platform."""
    query = update.callback_query
    await query.answer()

    style_key = query.data.split(":", 1)[1]
    if style_key not in STYLE_META:
        await query.edit_message_text("Unknown style. Use /style to start over.")
        return

    context.user_data["design_style"] = style_key
    meta = STYLE_META[style_key]

    await query.edit_message_text(
        f"✅ Style selected: {meta['emoji']} <b>{meta['label']}</b>\n\n"
        "📐 Now choose the platform:",
        parse_mode="HTML",
        reply_markup=_platform_keyboard(),
    )


async def cb_platform(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """User picked a platform → prompt for topic text."""
    query = update.callback_query
    await query.answer()

    platform_key = query.data.split(":", 1)[1]
    if platform_key not in PLATFORM_META:
        await query.edit_message_text("Unknown platform. Use /style to start over.")
        return

    context.user_data["design_platform"] = platform_key
    p_meta = PLATFORM_META[platform_key]
    s_meta = STYLE_META.get(context.user_data.get("design_style", ""), {})
    w, h = PLATFORM_SIZES[platform_key]

    await query.edit_message_text(
        f"✅ {s_meta.get('emoji','🎨')} <b>{s_meta.get('label','Style')}</b>  •  "
        f"{p_meta['emoji']} <b>{p_meta['label']}</b>  ({w}×{h})\n\n"
        "✏️ Now send me your design topic or text:",
        parse_mode="HTML",
    )


async def handle_design_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """User sends topic text → generate SVG → send PNG."""
    style_key    = context.user_data.get("design_style")
    platform_key = context.user_data.get("design_platform")

    # Guard: style not selected
    if not style_key:
        await update.message.reply_text(
            "Please select a style first:",
            reply_markup=_style_keyboard(),
        )
        return

    # Guard: platform not selected
    if not platform_key:
        await update.message.reply_text(
            "Please select a platform first:",
            reply_markup=_platform_keyboard(),
        )
        return

    topic = update.message.text.strip()
    w, h  = PLATFORM_SIZES[platform_key]
    s_meta = STYLE_META[style_key]
    p_meta = PLATFORM_META[platform_key]

    status_msg = await update.message.reply_text(
        f"⏳ Generating {w}×{h} design for <i>{topic}</i>…",
        parse_mode="HTML",
    )

    try:
        svg_code = await asyncio.to_thread(
            _generate_svg_with_claude, topic, style_key, platform_key
        )
        png_bytes = await asyncio.to_thread(svg_to_png, svg_code, w, h)
    except Exception as e:
        log.exception("Design generation failed")
        await status_msg.edit_text(f"❌ Error: {e}")
        return

    caption = (
        f"🎨 {s_meta['emoji']} {s_meta['label']}  •  "
        f"📐 {p_meta['emoji']} {p_meta['label']}"
    )

    tmp = Path(tempfile.mktemp(suffix=".png"))
    tmp.write_bytes(png_bytes)
    try:
        await update.message.reply_photo(photo=tmp.open("rb"), caption=caption)
    finally:
        tmp.unlink(missing_ok=True)

    await status_msg.delete()

    # Clear state so user can generate another
    context.user_data.pop("design_style", None)
    context.user_data.pop("design_platform", None)


# ── Registration ───────────────────────────────────────────────────────────────

def register_design_handlers(application: Application) -> None:
    """Call this once when setting up your bot Application."""
    application.add_handler(CommandHandler("style", cmd_style))
    application.add_handler(CallbackQueryHandler(cb_style,    pattern=r"^design_style:"))
    application.add_handler(CallbackQueryHandler(cb_platform, pattern=r"^design_platform:"))
    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_design_text,
        )
    )


# ── Standalone runner (for testing) ───────────────────────────────────────────

if __name__ == "__main__":
    import os
    from telegram.ext import ApplicationBuilder

    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    if not token:
        raise SystemExit("Set TELEGRAM_BOT_TOKEN env var")

    app = ApplicationBuilder().token(token).build()
    register_design_handlers(app)
    print("Bot running… /style to start")
    app.run_polling()
