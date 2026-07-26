import re
from pathlib import Path
count = 0
for py_file in Path("src/A_memorix").rglob("*.py"):
    lines = py_file.read_text(errors="replace").splitlines()
    modified = False
    i = 0
    while i < len(lines):
        m = re.match(r"(\s*)except\s+Exception(\s+as\s+\w+)?\s*:", lines[i])
        if m:
            indent = m.group(1) + "    "
            j = i + 1
            body = []
            while j < len(lines):
                s = lines[j].strip()
                if s == "" or s.startswith("#"):
                    body.append(lines[j])
                    j += 1
                    continue
                if lines[j] and not lines[j][0].isspace():
                    break
                body.append(lines[j])
                j += 1
            body_text = "\n".join(body)
            if "logger" not in body_text and "raise" not in body_text:
                lines.insert(i + 1, indent + "logger.warning(f'操作失败', exc_info=True)")
                modified = True
                count += 1
        i += 1
    if modified:
        py_file.write_text("\n".join(lines) + "\n")
print(f"Fixed: {count}")
