import inspect
from pytomator.core.api_registry import API_REGISTRY

def generate_api_html() -> str:
    sections = {}

    # agrupa por categoria
    for api in API_REGISTRY.values():
        sections.setdefault(api.category, []).append(api)

    html = """
    <html>
    <head>
        <style>
            body {
                font-family: Arial, sans-serif;
                font-size: 13px;
                background: #1e1e1e;
                color: #ddd;
            }
            h1 { color: #fff; }
            h2 {
                margin-top: 24px;
                border-bottom: 1px solid #444;
            }
            .cmd {
                margin: 12px 0;
                padding: 10px;
                background: #2b2b2b;
                border-radius: 6px;
            }
            .signature {
                font-family: monospace;
                color: #9cdcfe;
            }
            .desc {
                margin-top: 6px;
            }
            .params {
                margin-top: 6px;
            }
            .param {
                margin-left: 12px;
            }
            .example {
                margin-top: 6px;
                font-family: monospace;
                background: #1a1a1a;
                padding: 6px;
                border-radius: 4px;
            }
        </style>
    </head>
    <body>
        <h1>Pytomator API</h1>
    """

    for category, apis in sorted(sections.items()):
        html += f"<h2>{category}</h2>"

        for api in apis:
            sig = inspect.signature(api.func)

            html += f"""
            <div class="cmd">
                <div class="signature">{api.name}{sig}</div>
                <div class="desc">{api.description}</div>
            """

            if api.params:
                html += "<div class='params'><b>Arguments:</b>"
                for p, d in api.params.items():
                    html += f"<div class='param'>• <b>{p}</b>: {d}</div>"
                html += "</div>"

            if api.returns:
                html += f"<div><b>Returns:</b> {api.returns}</div>"

            for ex in api.examples:
                html += f"<div class='example'>{ex}</div>"

            html += "</div>"

    html += "</body></html>"
    return html
