import re
import webbrowser
import markdown
import dominate
from dominate.util import raw
from dominate.tags import *
from argparse import ArgumentParser
import shutil
import tempfile
import json
import os
from logging import *
import time
import bs4
import base64
from urllib.parse import unquote_plus

basicConfig(level="DEBUG")


class TriliumPdfExporter:
    EXCLUDE = ["file"]

    def __init__(self, source: str, motd: str) -> None:
        self.source: str = source
        self.motd: str = motd
        self.md = markdown.Markdown(extensions=["extra", "pymdownx.tilde"])
        self.idmap = {}

        self.tempdir: str = None
        self.meta = {}

    def _extract(self):
        tempdir = tempfile.TemporaryDirectory()
        shutil.unpack_archive(self.source, tempdir.name)
        return tempdir

    def _pathtuple(self, path):
        fullpath = unquote_plus(path).split(os.sep)
        pathparts = []
        while len(fullpath) > 0:
            pathparts.append(os.sep.join(fullpath))
            del fullpath[0]
        return tuple(pathparts)

    def _util_parse_meta_children(self, children: list, current: str) -> list:
        out = []
        for c in children:
            if not c["type"] in self.EXCLUDE:
                if "dataFileName" in c.keys():
                    parts = self._pathtuple(
                        os.path.join(current, c["dataFileName"]))
                    self.idmap[tuple(parts)] = c["noteId"]

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
                        "children": self._util_parse_meta_children(
                            c["children"],
                            os.path.join(
                                current,
                                c["dirFileName"] if "dirFileName" in c.keys() else "",
                            ),
                        )
                        if "children" in c.keys()
                        else [],
                    }
                )
        return out

    def _analyze_metadata(self):
        if not os.path.exists(os.path.join(self.tempdir.name, "!!!meta.json")):
            critical("Failed to load: !!!meta.json file missing.")
            exit(0)

        with open(os.path.join(self.tempdir.name, "!!!meta.json"), "r") as f:
            try:
                raw = json.load(f)
            except:
                critical("Failed to load: !!!meta.json is bad JSON")
                exit(0)

            self.idmap[("",)] = "root"

            out = {
                "title": f"Exported Notes: {time.strftime('%m / %d / %Y')}",
                "id": "root",
                "type": "book",
                "mime": None,
                "source": None,
                "path": "",
                "content": None,
                "children": self._util_parse_meta_children(raw["files"], ""),
            }
        return out

    def _convert_to_html(self, item: dict, current: str, top: bool = False) -> str:
        if top:
            content = div(self.motd if self.motd else "",
                          _class="note-content")
        else:
            content = ""
            if item["source"]:
                if item["source"].endswith(".md"):
                    with open(
                        os.path.join(self.tempdir.name, current,
                                     item["source"]), "r"
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
                elif item["type"] == "canvas":
                    with open(os.path.join(self.tempdir.name, current, item["source"]), "r") as f:
                        debug(f"Parsing canvase {item['source']}")
                        svg = json.load(f)["svg"]
                        content = div(img(
                            src=f"data:image/svg+xml;base64,{base64.b64encode(svg.encode('utf-8')).decode('utf-8')}",
                            _class="svg"
                        ),
                            _class="note-content note-svg"
                        )
                        item["content"] = content
                else:
                    with open(
                        os.path.join(self.tempdir.name, current,
                                     item["source"]), "rb"
                    ) as f:
                        item["content"] = "data:{};base64,{}".format(
                            item["mime"] if item["mime"] else "text/plain",
                            base64.b64encode(f.read()).decode("utf-8"),
                        )
                        self.idmap[
                            self._pathtuple(os.path.join(
                                current, item["source"]))
                        ] = item["content"]

        head = div(
            h2(item["title"]) if item["type"] == "book" else h4(item["title"]),
            _class="note-header",
            id=item["id"],
        )

        children = div(_class="note-children")
        for c in item["children"]:
            try:
                children += self._convert_to_html(
                    c, os.path.join(
                        current, item["path"] if item["path"] else "")
                )
            except ValueError:
                warning("Experienced tag creation error, skipping")

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
            style(
                """
                .note-children {
                    padding-left: 8px;
                    border-left: 2px solid #dddddd;
                }

                img {
                    display: block;
                }

                .note-content.note-svg {
                    display: block;
                    width: 90%;
                    height: auto;
                    box-sizing: border-box;
                    padding: 8px;
                    border: 2px solid #dddddd;
                    margin-left: 4px;
                    background-color: white;
                }

                .note-content.note-svg img {
                    display: inline-block;
                    height: auto;
                    width: 100%;
                }
            """
            )

        document += self._convert_to_html(self.meta, "", top=True)
        return document

    def _resolve_link(self, path):
        if not re.match("^[a-z]*?://.*", path):
            path = os.path.join(
                *[i for i in path.split(os.sep) if not i == ".."])
            return path
        else:
            return path

    def _resolve_links(self):
        soup = bs4.BeautifulSoup(self.doc, "html.parser")
        for l in soup.find_all("a"):
            if re.match("^[a-z]*?://.*", l["href"]):
                continue
            lnk = self._resolve_link(unquote_plus(l["href"]))
            key = self._pathtuple(lnk)
            l["href"] = "#root"
            for k in self.idmap.keys():
                if any([x in k for x in key]):
                    l["href"] = "#" + self.idmap[k]

        for i in soup.find_all("img"):
            if re.match("^[a-z]*?://.*", i["src"]) or i["src"].startswith("data:"):
                continue
            lnk = self._resolve_link(unquote_plus(i["src"]))
            key = self._pathtuple(lnk)
            i["src"] = ""
            for k in self.idmap.keys():
                if any([x in k for x in key]):
                    i["src"] = self.idmap[k]

        return str(soup)

    def export(self, preserve=False) -> str:
        info("Extracting zip file into temporary directory...")
        self.tempdir = self._extract()
        info("Analyzing export metadata")
        self.meta = self._analyze_metadata()
        self.doc = self._generate_html().render()
        self.doc = self._resolve_links()

        with tempfile.NamedTemporaryFile("r+", suffix=".html") as f:
            f.write(self.doc)
            f.flush()
            webbrowser.open(f"file://{f.name}")
            time.sleep(1)

        info("Cleaning up...")
        self.tempdir.cleanup()
        if not preserve:
            os.remove(self.source)


if __name__ == "__main__":
    parser = ArgumentParser(
        description="Parse a compressed MD export of Trilium notes, then convert to a web page for easy download"
    )
    parser.add_argument(
        "source", metavar="S", type=str, help="Path to source .zip file."
    )
    parser.add_argument(
        "-p",
        "--preserve",
        help="Whether to preserve the source zip file. Defaults to false.",
        action="store_true",
    )
    parser.add_argument(
        "-m",
        "--motd",
        type=str,
        help="Message to display under main title",
        default=None,
    )

    args = parser.parse_args()
    exporter = TriliumPdfExporter(args.source, args.motd)
    exporter.export(preserve=args.preserve)
