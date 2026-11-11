"""Inline the Missouri Strategies logo into site/index.html (no external image requests).
The logo is stored as base64 text (branding/missouri-strategies-logo.jpg.b64) so the repo has no binary files."""
import base64, os
R = os.path.dirname(os.path.abspath(__file__))
b64 = os.path.join(R, "branding", "missouri-strategies-logo.jpg.b64")
jpg = os.path.join(R, "branding", "missouri-strategies-logo.jpg")
data = open(b64).read().strip() if os.path.exists(b64) else base64.b64encode(open(jpg, "rb").read()).decode()
uri = "data:image/jpeg;base64," + data
t = open(os.path.join(R, "site", "template.html")).read().replace("__LOGO__", uri)
open(os.path.join(R, "site", "index.html"), "w").write(t)
print("site/index.html", len(t), "bytes")
