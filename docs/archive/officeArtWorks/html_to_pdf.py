# AI生成
"""
方案二：HTML → PDF
=================
1. 用 jinja2 渲染 HTML 模板（内嵌 CSS，A4 排版）
2. 用 Playwright 浏览器内核将 HTML 转为 PDF

用法：
    .venv\\Scripts\\python.exe html_to_pdf.py

输出：
    output_html.pdf
"""

import os
import sys

from jinja2 import Template

# 导入共享内容
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from content import CONTENT

# ── 配置 ──
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PDF_PATH = os.path.join(BASE_DIR, "output_html.pdf")
HTML_PATH = os.path.join(BASE_DIR, "output_html.html")  # 中间产物，方便调试

# ── HTML 模板（内嵌 CSS，A4 纵向） ──
HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <style>
        /* ── 全局 ── */
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: "Microsoft YaHei", "SimHei", "Noto Sans CJK SC", sans-serif;
            color: #333;
            line-height: 1.8;
        }

        /* ── A4 页面 ── */
        .page {
            width: 210mm;
            min-height: 297mm;
            padding: 25mm 20mm;
            page-break-after: always;
        }
        .page:last-child { page-break-after: auto; }

        /* ── 封面页 ── */
        .cover {
            display: flex;
            flex-direction: column;
            justify-content: center;
            align-items: center;
            text-align: center;
        }
        .cover h1 {
            font-size: 36pt;
            color: #1a1a2e;
            margin-bottom: 20px;
        }
        .cover .subtitle {
            font-size: 20pt;
            color: #4a90d9;
        }
        .cover .meta {
            margin-top: 60px;
            font-size: 12pt;
            color: #999;
        }

        /* ── 内容页 ── */
        .content-page h2 {
            font-size: 22pt;
            color: #1a1a2e;
            border-bottom: 3px solid #4a90d9;
            padding-bottom: 10px;
            margin-bottom: 20px;
        }
        .content-page .body {
            font-size: 12pt;
            margin-bottom: 20px;
        }
        .content-page ul {
            list-style: none;
            padding-left: 10px;
        }
        .content-page ul li {
            font-size: 12pt;
            margin-bottom: 10px;
            padding-left: 20px;
            position: relative;
        }
        .content-page ul li::before {
            content: "•";
            color: #4a90d9;
            font-size: 16pt;
            position: absolute;
            left: 0;
            top: -2px;
        }

        /* ── 表格 ── */
        table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 20px;
            font-size: 11pt;
        }
        table thead th {
            background: #4a90d9;
            color: #fff;
            padding: 12px 10px;
            text-align: center;
            font-weight: bold;
        }
        table tbody td {
            padding: 10px;
            text-align: center;
            border-bottom: 1px solid #e0e0e0;
        }
        table tbody tr:nth-child(even) {
            background: #f0f4f8;
        }

        /* ── 页脚 ── */
        .footer {
            position: fixed;
            bottom: 10mm;
            left: 20mm;
            right: 20mm;
            font-size: 9pt;
            color: #ccc;
            text-align: center;
            border-top: 1px solid #eee;
            padding-top: 5px;
        }
    </style>
</head>
<body>
{% for page in pages %}
{% if page.type == "title" %}
    <div class="page cover">
        <h1>{{ page.title }}</h1>
        <div class="subtitle">{{ page.subtitle }}</div>
        <div class="meta">
            {{ date }} · {{ author }}
        </div>
    </div>
{% elif page.type == "text" %}
    <div class="page content-page">
        <h2>{{ page.title }}</h2>
        {% if page.body %}<div class="body">{{ page.body }}</div>{% endif %}
        {% if page.bullets %}
        <ul>
            {% for b in page.bullets %}
            <li>{{ b }}</li>
            {% endfor %}
        </ul>
        {% endif %}
    </div>
{% elif page.type == "table" %}
    <div class="page content-page">
        <h2>{{ page.title }}</h2>
        <table>
            <thead>
                <tr>
                    {% for h in page.headers %}
                    <th>{{ h }}</th>
                    {% endfor %}
                </tr>
            </thead>
            <tbody>
                {% for row in page.rows %}
                <tr>
                    {% for cell in row %}
                    <td>{{ cell }}</td>
                    {% endfor %}
                </tr>
                {% endfor %}
            </tbody>
        </table>
    </div>
{% endif %}
{% endfor %}
    <div class="footer">{{ title }} · {{ date }}</div>
</body>
</html>
"""


def render_html():
    """用 jinja2 渲染 HTML"""
    template = Template(HTML_TEMPLATE)
    html = template.render(
        title=CONTENT["title"],
        date=CONTENT["date"],
        author=CONTENT["author"],
        pages=CONTENT["pages"],
    )

    # 保存中间 HTML（方便调试）
    with open(HTML_PATH, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"[OK] HTML 已渲染: {HTML_PATH}")
    return html


def html_to_pdf(html_content):
    """用 Playwright 将 HTML 转为 PDF"""
    from playwright.sync_api import sync_playwright

    pdf_abs = os.path.abspath(PDF_PATH)

    print("[..] 启动 Playwright Chromium...")
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.set_content(html_content, wait_until="domcontentloaded")
        page.pdf(
            path=pdf_abs,
            format="A4",
            print_background=True,
            margin={"top": "0", "bottom": "0", "left": "0", "right": "0"},
        )
        browser.close()

    print(f"[OK] PDF 已生成: {pdf_abs}")


def main():
    print("=" * 50)
    print("方案二：HTML → PDF")
    print("=" * 50)

    # Step 1: 渲染 HTML
    html = render_html()

    # Step 2: 转为 PDF
    html_to_pdf(html)

    print("\n完成！")
    print(f"  HTML: {HTML_PATH}")
    print(f"  PDF:  {PDF_PATH}")


if __name__ == "__main__":
    main()
