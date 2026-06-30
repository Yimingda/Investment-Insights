"""主题 CSS —— 支持 dark(黑夜) / light(白天) 两套色系。"""

_PALETTE = {
    "dark":  dict(bg="#0a0c10", card="#111318", border="#1e2130",
                  text="#e4e6ee", sub="#5a6070", link="#7aa2f7", shadow="none"),
    "light": dict(bg="#eef1f5", card="#ffffff", border="#dfe3ea",
                  text="#1b1e26", sub="#6b7280", link="#2f6fe0",
                  shadow="0 1px 3px rgba(0,0,0,.07)"),
}


def css(mode: str = "dark") -> str:
    v = _PALETTE.get(mode, _PALETTE["dark"])
    return f"""
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
  html, body, [class*="css"] {{ font-family: 'Inter', sans-serif; }}
  .stApp {{ background: {v['bg']}; }}
  .block-container {{ padding: 1.1rem 2rem; }}
  h1, h2, h3, h4, h5, h6, .stMarkdown, .stCaption, p, label {{ color: {v['text']}; }}
  [data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] * {{ color: {v['sub']}; }}

  .pcard {{
    background: {v['card']}; border: 1px solid {v['border']}; border-radius: 12px;
    padding: 14px 16px; margin-bottom: 14px; box-shadow: {v['shadow']};
  }}
  .pname {{ font-size: 15px; font-weight: 700; color: {v['text']}; }}
  .cat-badge {{
    display: inline-block; padding: 2px 8px; border-radius: 5px;
    font-size: 10px; font-weight: 600; margin-left: 6px;
  }}
  .sec-label {{
    font-size: 10px; color: {v['sub']}; text-transform: uppercase;
    letter-spacing: .06em; margin: 10px 0 4px; font-weight: 600;
  }}
  .news-row {{ padding: 5px 0; border-bottom: 1px solid {v['border']}; font-size: 12px; line-height: 1.45; }}
  .news-row a {{ color: {v['text']}; text-decoration: none; }}
  .news-row a:hover {{ color: {v['link']}; }}
  .meta {{ font-size: 9px; color: {v['sub']}; }}
  .tweet {{ padding: 6px 0; border-bottom: 1px solid {v['border']}; font-size: 12px; line-height: 1.5; color: {v['text']}; }}
  .summary {{
    background: {v['link']}14; border-left: 3px solid {v['link']};
    border-radius: 6px; padding: 8px 11px; font-size: 12px; line-height: 1.6; color: {v['text']};
  }}
  .stance {{
    background: #d9a4060f; border-left: 3px solid #d9a406bb;
    border-radius: 6px; padding: 7px 10px; margin: 7px 0 2px;
    font-size: 11.5px; line-height: 1.55; color: {v['text']};
  }}
  .stance-tag {{ font-weight: 700; color: #c2871a; margin-right: 5px; white-space: nowrap; }}
  .empty {{ font-size: 11px; color: {v['sub']}; padding: 4px 0; }}
  .tl-row {{ display: flex; gap: 10px; align-items: flex-start;
    padding: 9px 2px; border-bottom: 1px solid {v['border']}; }}
  .tl-text {{ font-size: 12.5px; line-height: 1.45; color: {v['text']}; }}
  .tl-text a {{ color: {v['text']}; text-decoration: none; }}
  .tl-text a:hover {{ color: {v['link']}; }}
  a.plink {{ text-decoration: none; }}
  footer {{ visibility: hidden; }} #MainMenu {{ visibility: hidden; }}
</style>
"""
