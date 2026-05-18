"""Post design generator: HTML → PNG via Playwright, sent to Telegram."""
from __future__ import annotations

import asyncio
import re
import tempfile
from pathlib import Path
from typing import Any

import httpx

from ...config import settings
from ..base import Skill


_STYLE_PROMPTS = {
    "modern":    "modern, dark background (#0F172A), gradient accent colors (purple/indigo), clean sans-serif fonts, minimal",
    "light":     "clean white background, soft shadows, pastel accent colors, professional, modern",
    "gradient":  "bold gradient background (purple to pink or blue to teal), white text, vibrant, eye-catching",
    "corporate": "professional blue/white, corporate clean style, trust-inspiring, serif+sans mix",
    "neon":      "dark background, neon glow effects (cyan/pink/green), futuristic, cyberpunk feel",
}


def _generate_html_with_claude(topic: str, text: str, style: str, size: str) -> str:
    import anthropic

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    w, h = {"square": (1080, 1080), "story": (1080, 1920), "wide": (1200, 628)}.get(size, (1080, 1080))
    style_desc = _STYLE_PROMPTS.get(style, _STYLE_PROMPTS["modern"])

    prompt = f"""Create a beautiful social media post design as a single self-contained HTML file.

Topic: {topic}
Content text: {text if text else "(generate suitable short text for the topic)"}
Visual style: {style_desc}
Canvas size: {w}x{h}px

Requirements:
- Single HTML file, ALL CSS must be inline in <style> tag — NO external resources, NO @import, NO Google Fonts
- Use system fonts only: font-family: 'Segoe UI', Arial, sans-serif
- The <html> and <body> must be exactly {w}px wide and {h}px tall, overflow:hidden, margin:0, padding:0
- Beautiful typography hierarchy: large bold headline, subtitle/body text, optional small tag line
- Use CSS gradients, shapes (::before/::after pseudo-elements), geometric decorations — no images
- Text must have HIGH contrast against background — white text on dark, dark text on light
- Make it look like a premium professional social media post
- No placeholder text

Return ONLY the complete HTML code starting with <!DOCTYPE html>, nothing else."""

    msg = client.messages.create(
        model=settings.model,
        max_tokens=4000,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = msg.content[0].text.strip()
    raw = re.sub(r"^```[a-z]*\n?", "", raw)
    raw = re.sub(r"\n?```$", "", raw)
    return raw


async def _render_html_to_png(html: str, width: int, height: int) -> Path:
    from playwright.async_api import async_playwright

    tmp = Path(tempfile.mktemp(suffix=".png"))
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox"],
        )
        page = await browser.new_page(viewport={"width": width, "height": height})
        # wait=domcontentloaded is faster and avoids hanging on slow external fonts
        await page.set_content(html, wait_until="domcontentloaded")
        # Give fonts/CSS a moment to apply
        await page.wait_for_timeout(1500)
        await page.screenshot(
            path=str(tmp),
            clip={"x": 0, "y": 0, "width": width, "height": height},
            full_page=False,
        )
        await browser.close()
    return tmp


async def _send_photo_telegram(file_path: Path, caption: str) -> dict:
    token   = settings.telegram_bot_token
    chat_id = settings.telegram_chat_id
    if not token or not chat_id:
        return {"ok": False, "reply": "Telegram sozlanmagan."}

    url = f"https://api.telegram.org/bot{token}/sendPhoto"
    async with httpx.AsyncClient(timeout=60) as client:
        with open(file_path, "rb") as f:
            resp = await client.post(
                url,
                data={"chat_id": chat_id, "caption": caption, "parse_mode": "HTML"},
                files={"photo": (file_path.name, f, "image/png")},
            )
    data = resp.json()
    if not data.get("ok"):
        return {"ok": False, "reply": f"Telegram xato: {data.get('description')}"}
    return {"ok": True}


class PostDesignSkill(Skill):
    name = "post_design"
    description = "Create a beautiful social media post image using AI-generated HTML rendered to PNG."
    tool_description = (
        "Create a professional social media post design image (PNG) and send it via Telegram.\n"
        "Use this when the user wants to create a post, banner, flyer, or visual design for any topic.\n"
        "\n"
        "Styles: modern (dark), light, gradient, corporate, neon\n"
        "Sizes: square (1080x1080, Instagram), story (1080x1920, Stories/Reels), wide (1200x628, Facebook/LinkedIn)\n"
        "\n"
        "Examples:\n"
        "  'AI haqida Instagram post qil' → topic='AI haqida', style='modern', size='square'\n"
        "  'Chegirma e'loni uchun post' → topic='Chegirma', style='gradient', size='square'\n"
        "  'LinkedIn uchun professional banner' → topic='...', style='corporate', size='wide'\n"
    )
    args_schema = {
        "type": "object",
        "properties": {
            "topic": {
                "type": "string",
                "description": "Post topic or title.",
            },
            "text": {
                "type": "string",
                "description": "Optional body text or key message for the post.",
            },
            "style": {
                "type": "string",
                "enum": ["modern", "light", "gradient", "corporate", "neon"],
                "description": "Visual style. Default: modern.",
                "default": "modern",
            },
            "size": {
                "type": "string",
                "enum": ["square", "story", "wide"],
                "description": "Canvas size. square=Instagram, story=Stories, wide=Facebook/LinkedIn. Default: square.",
                "default": "square",
            },
        },
        "required": ["topic"],
    }

    async def run(self, text: str, match: Any | None = None) -> dict[str, Any]:
        return await self.run_tool({"topic": text})

    async def run_tool(self, args: dict[str, Any]) -> dict[str, Any]:
        topic = (args.get("topic") or "").strip()
        text  = (args.get("text") or "").strip()
        style = (args.get("style") or "modern").strip()
        size  = (args.get("size") or "square").strip()

        if not topic:
            return {"ok": False, "reply": "Mavzu kiriting."}

        w, h = {"square": (1080, 1080), "story": (1080, 1920), "wide": (1200, 628)}.get(size, (1080, 1080))

        try:
            html = await asyncio.to_thread(
                _generate_html_with_claude, topic, text, style, size
            )
            file_path = await _render_html_to_png(html, w, h)

            caption = f"🎨 <b>{topic}</b> — {style} | {size}"
            result  = await _send_photo_telegram(file_path, caption)
            file_path.unlink(missing_ok=True)

            if not result.get("ok"):
                return result

            return {"ok": True, "reply": f"✅ <b>{topic}</b> — post dizayn yuborildi."}

        except Exception as e:
            return {"ok": False, "reply": f"Dizayn xatosi: {e}"}
