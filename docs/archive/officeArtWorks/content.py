# AI生成
"""
共享内容数据 —— 两种方案共用同一份内容，方便对比效果。
替换 pages 列表中的内容即可生成你自己的文档。
"""

CONTENT = {
    "title": "办公文档生成方案对比",
    "subtitle": "PPT→PDF vs HTML→PDF",
    "date": "2026-08-10",
    "author": "OfficeArtWorks",
    "pages": [
        {
            "type": "title",
            "title": "办公文档生成方案对比",
            "subtitle": "PPT→PDF vs HTML→PDF",
        },
        {
            "type": "text",
            "title": "方案一：PPT → PDF",
            "body": "使用 python-pptx 生成幻灯片文件，再通过 comtypes 调用 PowerPoint COM 接口转换为 PDF。",
            "bullets": [
                "优势：排版直观，所见即所得",
                "优势：可复用 PowerPoint 模板",
                "劣势：依赖 PowerPoint 软件",
                "劣势：转换速度较慢",
            ],
        },
        {
            "type": "text",
            "title": "方案二：HTML → PDF",
            "body": "使用 jinja2 渲染 HTML 模板，再通过 Playwright 浏览器内核生成 PDF。",
            "bullets": [
                "优势：CSS 排版灵活精细",
                "优势：不依赖 Office 软件",
                "优势：支持复杂网页样式",
                "劣势：需要浏览器内核（约 150MB）",
            ],
        },
        {
            "type": "table",
            "title": "方案对比总结",
            "headers": ["维度", "方案一 PPT→PDF", "方案二 HTML→PDF"],
            "rows": [
                ["依赖", "PowerPoint", "Playwright + Chromium"],
                ["排版方式", "幻灯片式", "网页式（CSS）"],
                ["灵活性", "中等", "高"],
                ["速度", "较慢", "快"],
                ["适用场景", "演示文稿类", "文档/报告类"],
            ],
        },
    ],
}
