"""mapcanvas web server. Run: python app.py, then open http://127.0.0.1:5000"""

from flask import Flask, Response, jsonify, render_template, request

import mapart

app = Flask(__name__)


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/presets")
def presets():
    return jsonify(mapart.PRESETS)


@app.post("/api/render")
def api_render():
    d = request.get_json(force=True)
    style = dict(mapart.PRESETS.get(d.get("preset"), mapart.PRESETS["gallery"]))
    style.update(
        {k: v for k, v in (d.get("style") or {}).items() if isinstance(v, str)}
    )
    try:
        png = mapart.render(
            place=str(d.get("place", "")).strip() or "Berlin, Germany",
            dist=float(d.get("dist", 2000)),
            style=style,
            size=int(d.get("size", 1600)),
            circle=bool(d.get("circle", True)),
            width_scale=float(d.get("width_scale", 1.0)),
        )
    except mapart.RenderError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": f"Something went wrong: {e}"}), 500
    return Response(png, mimetype="image/png")


if __name__ == "__main__":
    app.run(debug=False, port=5000)
