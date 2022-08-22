import re
import markdown
import dominate
from dominate.util import raw
from dominate.tags import *
from pdfkit import from_string
from argparse import ArgumentParser
import shutil
import tempfile
import json
import os
from logging import *
import time
import bs4
import base64

basicConfig(level="DEBUG")


class TriliumPdfExporter:
    EXCLUDE = ["file"]

    def __init__(self, source: str, target: str) -> None:
        self.source: str = source
        self.target: str = target
        self.md = markdown.Markdown(extensions=["extra", "pymdownx.tilde"])

        self.tempdir: str = None
        self.meta = {}

    def _extract(self):
        tempdir = tempfile.TemporaryDirectory()
        shutil.unpack_archive(self.source, str(tempdir))
        return tempdir

    def _util_parse_meta_children(self, children: list) -> list:
        out = []
        for c in children:
            if not c["type"] in self.EXCLUDE:
                out.append(
                    {
                        "title": c["title"],
                        "id": c["noteId"],
                        "type": c["type"],
                        "mime": c["mime"] if "mime" in c.keys() else None,
                        "source": c["dataFileName"]
                        if "dataFileName" in c.keys()
                        else None,
                        "path": c["dirFileName"] if "dirFileName" in c.keys() else None,
                        "content": None,
                        "children": self._util_parse_meta_children(c["children"])
                        if "children" in c.keys()
                        else [],
                    }
                )
        return out

    def _analyze_metadata(self):
        if not os.path.exists(os.path.join(str(self.tempdir), "!!!meta.json")):
            critical("Failed to load: !!!meta.json file missing.")
            exit(0)

        with open(os.path.join(str(self.tempdir), "!!!meta.json"), "r") as f:
            try:
                raw = json.load(f)
            except:
                critical("Failed to load: !!!meta.json is bad JSON")
                exit(0)

            out = {
                "title": f"Exported Notes: {time.strftime('%m / %d / %Y')}",
                "id": "root",
                "type": "book",
                "mime": None,
                "source": None,
                "path": "",
                "content": None,
                "children": self._util_parse_meta_children(raw["files"]),
            }
        return out

    def _convert_to_html(self, item: dict, current: str) -> str:
        content = ""
        if item["source"]:
            if item["source"].endswith(".md"):
                with open(
                    os.path.join(str(self.tempdir), current, item["source"]), "r"
                ) as f:
                    debug(f"Parsing {item['source']}")
                    raw_md = f.read().replace("\\\\(", "$").replace("\\\\)", "$")
                    for k in re.findall("~.*?~", raw_md):
                        raw_md = raw_md.replace(k, "~" + k + "~")

                    content = div(
                        raw(
                            self.md.convert(
                                raw_md,
                            ).replace("h1", "h5")
                        ),
                        _class="note-content",
                    )
                    item["content"] = content
            else:
                with open(
                    os.path.join(str(self.tempdir), current, item["source"]), "rb"
                ) as f:
                    item["content"] = "data:{};base64,{}".format(
                        item["mime"] if item["mime"] else "text/plain",
                        base64.b64encode(f.read()).decode("utf-8"),
                    )

        head = div(
            h2(item["title"]) if item["type"] == "book" else h4(item["title"]),
            _class="note-header",
            id=item["id"],
        )

        children = div(_class="note-children")
        for c in item["children"]:
            children += self._convert_to_html(
                c, os.path.join(current, item["path"] if item["path"] else "")
            )

        return div(head, content, children, _class="note")

    def _generate_html(self):
        document = dominate.document(
            title=f"Exported Notes: {time.strftime('%m / %d / %Y')}"
        )

        with document.head:
            link(
                rel="stylesheet",
                href="https://cdn.jsdelivr.net/npm/katex@0.16.0/dist/katex.min.css",
                integrity="sha384-Xi8rHCmBmhbuyyhbI88391ZKP2dmfnOl4rT9ZfRI7mLTdk1wblIUnrIq35nqwEvC",
                crossorigin="anonymous",
            )
            script(
                defer=True,
                src="https://cdn.jsdelivr.net/npm/katex@0.16.0/dist/katex.min.js",
                integrity="sha384-X/XCfMm41VSsqRNQgDerQczD69XqmjOOOwYQvr/uuC+j4OPoNhVgjdGFwhvN02Ja",
                crossorigin="anonymous",
            )
            script(
                defer=True,
                src="https://cdn.jsdelivr.net/npm/katex@0.16.0/dist/contrib/auto-render.min.js",
                integrity="sha384-+XBljXPPiv+OzfbB3cVmLHf4hdUFHlWNZN5spNQ7rmHTXpd7WvJum6fIACpNNfIR",
                crossorigin="anonymous",
                onload="console.log(renderMathInElement(document.body, {delimiters: [{left: '$', right: '$', display: false}]}));",
            )

        document += self._convert_to_html(self.meta, "")
        return document

    def export(self, preserve=False) -> str:
        info("Extracting zip file into temporary directory...")
        self.tempdir = self._extract()
        info("Analyzing export metadata")
        self.meta = self._analyze_metadata()
        debug(json.dumps(self.meta, indent=4))
        self.doc = self._generate_html().render()
        with open("out.html", "w") as f:
            f.write(self.doc)

        self.tempdir.cleanup()


if __name__ == "__main__":
    parser = ArgumentParser(
        description="Parse a compressed MD export of Trilium notes, then convert to a single PDF file"
    )
    parser.add_argument(
        "source", metavar="S", type=str, help="Path to source .zip file."
    )
    parser.add_argument(
        "--output",
        type=str,
        required=False,
        help="Path to pdf file to output. Defaults to trilium_export.pdf",
        default="trilium_export.pdf",
    )
    parser.add_argument(
        "--preserve",
        type=bool,
        required=False,
        help="Whether to preserve the source zip file. Defaults to false.",
        default=False,
    )

    args = parser.parse_args()
    exporter = TriliumPdfExporter(args.source, args.output)
    exporter.export()
