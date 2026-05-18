"""Presentation generator: Claude generates slides, Playwright renders each as PNG, sent as Telegram album."""
from __future__ import annotations

import asyncio
import json
import re
import tempfile
from pathlib import Path
from typing import Any

import httpx

from ...config import settings
from ..base import Skill

W, H = 1280, 720  # 16:9 slide canvas


def _slide_html(slide: dict, index: int, total: int, title: str) -> str:
    is_title = index == 0
    bg = "#0F172A"
    accent = "#6366F1"

    if is_title:
        subtitle = slide.get("subtitle", "")
        return f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
html,body{{width:{W}px;height:{H}px;overflow:hidden;background:{bg};font-family:'Segoe UI',Arial,sans-serif}}
.wrap{{width:{W}px;height:{H}px;display:flex;flex-direction:column;align-items:center;justify-content:center;padding:60px}}
.num{{position:absolute;bottom:28px;right:40px;color:#475569;font-size:16px}}
.line{{width:120px;height:5px;background:linear-gradient(90deg,{accent},#818CF8);border-radius:3px;margin-bottom:32px}}
h1{{font-size:62px;font-weight:800;color:#F1F5F9;text-align:center;line-height:1.15;letter-spacing:-1px}}
p{{font-size:26px;color:#94A3B8;margin-top:20px;text-align:center;font-weight:300}}
.dots{{position:absolute;top:0;left:0;width:100%;height:100%;pointer-events:none;overflow:hidden}}
.dot{{position:absolute;border-radius:50%;opacity:0.06;background:{accent}}}
</style></head><body>
<div class="dots">
  <div class="dot" style="width:400px;height:400px;top:-120px;right:-80px"></div>
  <div class="dot" style="width:250px;height:250px;bottom:-60px;left:60px"></div>
</div>
<div class="wrap">
  <div class="line"></div>
  <h1>{slide.get("title","") if not is_title else title}</h1>
  {"<p>" + subtitle + "</p>" if subtitle else ""}
</div>
<div class="num">1 / {total}</div>
</body></html>"""

    slide_title = slide.get("title", "")
    points = slide.get("points", [])
    points_html = "".join(
        f'<li style="margin-bottom:14px;color:#CBD5E1;font-size:21px;line-height:1.5">'
        f'<span style="color:{accent};margin-right:10px">▸</span>{p}</li>'
        for p in points
    )

    return f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
html,body{{width:{W}px;height:{H}px;overflow:hidden;background:{bg};font-family:'Segoe UI',Arial,sans-serif}}
.bar{{position:absolute;left:0;top:0;width:6px;height:100%;background:linear-gradient(180deg,{accent},#818CF8)}}
.header{{padding:36px 60px 20px 76px;border-bottom:1px solid #1E293B}}
h2{{font-size:34px;font-weight:700;color:#6366F1;line-height:1.2}}
.content{{padding:28px 60px 28px 76px}}
ul{{list-style:none}}
.num{{position:absolute;bottom:22px;right:40px;color:#334155;font-size:15px}}
.logo{{position:absolute;bottom:22px;left:76px;color:#334155;font-size:14px;letter-spacing:2px;text-transform:uppercase}}
</style></head><body>
<div class="bar"></div>
<div class="header"><h2>{slide_title}</h2></div>
<div class="content"><ul>{points_html}</ul></div>
<div class="logo">{title[:40]}</div>
<div class="num">{index + 1} / {total}</div>
</body></html>"""


async def _render_slide(html: str) -> bytes:
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
        page = await browser.new_page(viewport={"width": W, "height": H})
        await page.set_content(html, wait_until="domcontentloaded")
        await page.wait_for_timeout(300)
        png = await page.screenshot(
            clip={"x": 0, "y": 0, "width": W, "height": H}, full_page=False
        )
        await browser.close()
    return png


def _generate_slides_with_claude(topic: str, slide_count: int, language: str) -> tuple[str, list[dict]]:
    import anthropic

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    lang_instruction = {
        "uz": "Respond in Uzbek language.",
        "ru": "Respond in Russian language.",
        "en": "Respond in English language.",
    }.get(language, "Detect language from topic and respond in that language.")

    prompt = f"""Create a professional presentation about: "{topic}"

{lang_instruction}

Return ONLY valid JSON — no markdown fences, no extra text:
{{
  "title": "Short presentation title (max 8 words)",
  "slides": [
    {{"title": "Title slide heading", "subtitle": "One-line subtitle"}},
    {{"title": "Slide title", "points": ["point 1", "point 2", "point 3", "point 4"]}},
    {{"title": "Slide title", "points": ["point 1", "point 2", "point 3"]}}
  ]
}}

Rules:
- First slide is the title slide (has subtitle, no points)
- Exactly {slide_count} slides total
- Content slides: 3-5 bullet points each, max 12 words per point
- Be informative, accurate, professional"""

    msg = client.messages.create(
        model=settings.model,
        max_tokens=2500,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = msg.content[0].text.strip()
    raw = re.sub(r"^```[a-z]*\n?", "", raw)
    raw = re.sub(r"\n?```$", "", raw)
    m = re.search(r'\{[\s\S]*\}', raw)
    if m:
        raw = m.group(0)
    data = json.loads(raw)
    return data["title"], data["slides"]


async def _send_album_telegram(images: list[bytes], caption: str) -> dict:
    token   = settings.telegram_bot_token
    chat_id = settings.telegram_chat_id
    if not token or not chat_id:
        return {"ok": False, "reply": "Telegram sozlanmagan."}

    # Telegram media group: up to 10 per message
    url = f"https://api.telegram.org/bot{token}/sendMediaGroup"
    tmp_files: list[Path] = []

    try:
        async with httpx.AsyncClient(timeout=120) as client:
            for batch_start in range(0, len(images), 10):
                batch = images[batch_start : batch_start + 10]
                media_json = []
                files: dict = {}
                for i, png in enumerate(batch):
                    name = f"slide_{batch_start + i}.png"
                    files[name] = (name, png, "image/png")
                    entry: dict = {"type": "photo", "media": f"attach://{name}"}
                    if i == 0 and batch_start == 0:
                        entry["caption"] = caption
                        entry["parse_mode"] = "HTML"
                    media_json.append(entry)

                resp = await client.post(
                    url,
                    data={"chat_id": chat_id, "media": json.dumps(media_json)},
                    files=files,
                )
                data = resp.json()
                if not data.get("ok"):
                    return {"ok": False, "reply": f"Telegram xato: {data.get('description')}"}
    finally:
        for f in tmp_files:
            f.unlink(missing_ok=True)

    return {"ok": True}


class PresentationSkill(Skill):
    name = "presentation"
    description = "Create a visual slide presentation on any topic and send as images via Telegram."
    tool_description = (
        "Create a beautiful visual presentation on any topic. "
        "Each slide is rendered as a 1280x720 PNG image and sent as a Telegram photo album.\n"
        "Use this when the user asks to create a presentation, slides, or slideshow about any topic.\n"
        "Examples:\n"
        "  'AI haqida prezentatsiya qil' → topic='AI haqida', slide_count=8\n"
        "  'Python dasturlash haqida 6 ta slayd' → topic='Python dasturlash', slide_count=6\n"
        "  'Create a presentation about climate change' → topic='climate change'\n"
    )
    args_schema = {
        "type": "object",
        "properties": {
            "topic": {"type": "string", "description": "Presentation topic."},
            "slide_count": {
                "type": "integer",
                "description": "Number of slides including title. Default: 8.",
                "default": 8,
            },
            "language": {
                "type": "string",
                "enum": ["uz", "ru", "en", "auto"],
                "default": "auto",
            },
        },
        "required": ["topic"],
    }

    async def run(self, text: str, match: Any | None = None) -> dict[str, Any]:
        return await self.run_tool({"topic": text})

    async def run_tool(self, args: dict[str, Any]) -> dict[str, Any]:
        topic       = (args.get("topic") or "").strip()
        slide_count = max(4, min(int(args.get("slide_count") or 8), 20))
        language    = (args.get("language") or "auto").strip()

        if not topic:
            return {"ok": False, "reply": "Mavzu kiriting."}

        try:
            title, slides_data = await asyncio.to_thread(
                _generate_slides_with_claude, topic, slide_count, language
            )

            # Render all slides concurrently
            htmls = [_slide_html(s, i, len(slides_data), title) for i, s in enumerate(slides_data)]
            images = await asyncio.gather(*[_render_slide(h) for h in htmls])

            caption = f"📊 <b>{title}</b> — {len(images)} ta slayd"
            result  = await _send_album_telegram(list(images), caption)

            if not result.get("ok"):
                return result

            return {"ok": True, "reply": f"✅ <b>{title}</b> — {len(images)} ta slayd yuborildi."}

        except json.JSONDecodeError as e:
            return {"ok": False, "reply": f"JSON xatosi: {e}. Qayta urining."}
        except Exception as e:
            return {"ok": False, "reply": f"Xato: {e}"}
