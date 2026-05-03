from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from adapters.solidworks_com import SolidWorksComAdapter, _maybe_call  # noqa: E402


def main() -> int:
    adapter = SolidWorksComAdapter()
    output = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT.parent / "outputs" / "jobs" / "_save_probe" / "blank_probe.SLDPRT"
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    with adapter._solidworks_session():
        sw = adapter._connect(visible=True)
        template = adapter.find_part_template()
        model = sw.NewDocument(str(template), 0, 0, 0)
        if model is None:
            print(json.dumps({"ok": False, "error": "NewDocument returned None", "template": str(template)}, ensure_ascii=False, indent=2))
            return 1
        created_title = str(_maybe_call(getattr(model, "GetTitle", None)) or getattr(model, "GetTitle", "") or getattr(model, "Title", "") or "")
        try:
            ok = adapter._save_as(model, output, sw=sw)
        finally:
            try:
                sw.CloseDoc(created_title)
            except Exception:
                pass

        result = {
            "ok": ok,
            "output": str(output),
            "exists": output.exists(),
            "size": output.stat().st_size if output.exists() else 0,
            "save_report": adapter._last_save_report,
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
