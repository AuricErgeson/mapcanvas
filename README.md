# mapcanvas

A little tool I built because I wanted posters of places I care about,
without paying poster-shop prices. You type in a city, pick a radius,
choose a palette (or mix your own), and it draws the streets, rivers,
parks and buildings as flat shapes and saves the whole thing as a PNG.
No tiles, no zooming, no GIS dashboard. Just a picture of a place.

It pulls live data from OpenStreetMap, so every render is the real
street plan of the place you typed in.

## Running it

Install the pinned Python dependencies, then start the server:

```
py -m pip install -r requirements.txt
py app.py
```

and open http://127.0.0.1:5000 in your browser.

The first render for a new city takes a little while because it
downloads the map data. After that the data is cached, so playing with
colors and shapes is basically instant.

## A quick tour

1. Type a place, say `Lisbon, Portugal`, and pick a radius.
2. Hit **Render poster**.
3. Try the presets: `gallery`, `noir`, `blueprint`, `sakura`, `cobalt`.
4. Tweak single layers with the color pickers, make roads thicker or
   thinner, switch between the round medallion and the square poster.
5. **Download PNG** when you like what you see.

The **Random** button next to the place field picks a random city,
which is fun when you just want to look around.

If you don't care about the web page, the drawing part works on its own:

```python
import mapart

png = mapart.render("Lisbon, Portugal", 1500, mapart.PRESETS["noir"])
open("lisbon.png", "wb").write(png)
```

`python test_render.py` draws a tiny fake city offline, just to make
sure the drawing code still works after changes.

## How it works, roughly

`mapart.py` asks OpenStreetMap (through osmnx) for everything inside
your circle: roads, buildings, water, green areas. It then projects
that onto a flat pixel canvas and paints the layers one over the other,
water first, roads last, with a caption and coordinates at the bottom.
`app.py` is a tiny Flask server around it. The front end is split into
`templates/index.html`, `static/app.css` and `static/app.js`.

## Checks

GitHub Actions runs the same offline checks for every pull request and
every push to `main`. You can run them locally without downloading map data:

```
py -m compileall -q app.py mapart.py test_render.py test_web.py
node --check static/app.js
py -m unittest -v test_web
py test_render.py
```

## Collaborating

This is a personal project and I'm happy to share it. If you have
ideas, run into bugs, or want to add something: open an issue or a pull
request, anyone is welcome. Good places to start would be new presets,
better lettering on the poster, or more layers like railways and tram
lines.

Next step on my own list: turning this into a proper Python package,
so `pip install mapcanvas` just works and you can use `mapart.render`
from any project.

## One important thing

The map data belongs to the [OpenStreetMap
contributors](https://www.openstreetmap.org/copyright) (ODbL license).
Every poster prints a small credit line for them at the bottom. Please
leave it in when you share your renders.

made with love by Auric
