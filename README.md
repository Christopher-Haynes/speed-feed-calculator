# Speed & Feed Calculator

A clean, ad-free feeds and speeds calculator for machinists, CNC programmers, and engineers.

## Why I built this

I'm a CNC machinist and a computer science student. When I need a starting speed and feed at the machine, the sites I'd pull up on my phone are buried in ads, pop-ups, and sign-up walls. I wanted something fast, readable from arm's length, and usable with gloves on, that shows where every number comes from instead of asking me to trust it.

## Features

- **Milling, drilling, and turning** tabs, with inputs on the left and results on the right (stacked on phones)
- **Live results** as you type: RPM, feed, surface speed, chip load, chip-thinning adjustment, and MRR
- **Inch/metric toggle** that converts the values you've already typed
- **Fractions accepted:** type `1/2` or `1-1/4` instead of decimals
- **Dark mode by default**, with big text and tap targets
- **Low / middle / high range** from the material data
- **Lathe:** RPM at start and finish diameter, G96 surface speed, a suggested G50 RPM clamp and the diameter where it kicks in, and G97 threading
- **Circular interpolation:** feed adjusted for milling inside a hole or around a boss
- **Warnings** for capped RPM, feed over the machine max, rubbing (chip too thin), horsepower over the spindle, long stickout, small tools in hard material, and ball mill effective diameter
- **Where every number comes from:** source, link, date checked, and confidence (handbook, manufacturer, or shop-verified), plus other sources to cross-check
- **Copy for setup sheet:** results formatted as G-code comments
- **Saved machines and favorites,** stored in your browser with no sign-up
- **Formula reference** and **data sources** pages in plain English
- **Report a bad number** button on every result

## What data is in it

| | Coverage |
|---|---|
| Milling | Carbide end mills (flat, ball, bull nose), 1/8" to 1", for 18 materials across ISO P, M, K, N, and S: 6061, 7075, brass, polycarbonate, acrylic, 1018, 1045, 4340, 303, 304, 316, 17-4 PH, gray and ductile iron, Ti-6Al-4V, CP titanium, Inconel 718 and 625 |
| Machine presets | Tormach 1100MX, 770MX, and 8L |
| Drilling, turning, face mills, HSS | No data yet. Type your own surface speed and feed. |

Where a source gives only a surface speed range, the calculator starts in the middle and says so.

## Running it

Requires Python 3.10 or newer.

```bash
git clone https://github.com/Christopher-Haynes/speed-feed-calculator.git
cd speed-feed-calculator
python -m venv .venv
```

Activate the virtual environment:

```bash
# Windows (PowerShell)
.venv\Scripts\Activate.ps1

# macOS / Linux
source .venv/bin/activate
```

Install, then start the app and open http://127.0.0.1:5000:

```bash
python -m pip install -r requirements-dev.txt
flask --app app run --debug
```

Run the tests:

```bash
python -m pytest
```

## Deploying

### PythonAnywhere (keeps bad-number reports between restarts)

1. Make a free account at pythonanywhere.com and open a **Bash console**.
2. Clone the repo and install it:
   ```bash
   git clone https://github.com/Christopher-Haynes/speed-feed-calculator.git
   cd speed-feed-calculator
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```
3. On the **Web** tab, choose **Add a new web app → Manual configuration**, and pick the same Python version that `python3 --version` shows.
4. Set **Virtualenv** to `/home/<your-username>/speed-feed-calculator/.venv`.
5. Open the **WSGI configuration file** link, delete everything in it, and put:
   ```python
   import sys
   path = "/home/<your-username>/speed-feed-calculator"
   if path not in sys.path:
       sys.path.insert(0, path)
   from wsgi import app as application
   ```
6. Click **Reload**. To update later: `git pull` in the console, then **Reload**.

### Render

In the Render dashboard choose **New → Blueprint** and pick this repo; [`render.yaml`](render.yaml) has the settings. Free instances sleep when idle, and Render's disk resets on every deploy, so saved bad-number reports are lost on redeploy.

## Adding data

Cutting data and machine presets live in plain CSV files in [`data/`](data/). [`data/schema.sql`](data/schema.sql) explains every column. The app rebuilds its database from these files each time it starts, and stops with the file name and line number if a row is wrong. To check your edits:

```bash
flask --app app check-data
```

To read bad-number reports people have sent:

```bash
flask --app app reports
```

## How it's built

| File | What it does |
|---|---|
| [`formulas.py`](formulas.py) | The math, as plain functions with no web code |
| [`units.py`](units.py) | Inch/metric conversion, display formatting, reading typed fractions |
| [`calculator.py`](calculator.py) | Reads the form, picks the data, runs the formulas, builds warnings |
| [`data_store.py`](data_store.py) | Loads the CSVs into SQLite with checks, and looks rows up |
| [`reports.py`](reports.py) | Saves "report a bad number" submissions |
| [`app.py`](app.py) | Flask routes |
| [`wsgi.py`](wsgi.py) | Entry point for production servers |
| [`templates/`](templates/), [`static/`](static/) | Pages, styles, and the small script for live updates |
| [`tests/`](tests/) | pytest tests for all of the above |

Everything runs in inch units inside. Metric input is converted on the way in and results on the way out, so the formulas and the data only deal with one system. The page works without JavaScript; the script adds live updates, saved machines, favorites, and the copy button.

## Formulas

The full plain-English reference is on the site's Formulas page. The core ones:

| Calculation | Formula |
|---|---|
| RPM (inch) | 12 × SFM / (π × D) |
| RPM (metric) | 1000 × Vc / (π × D) |
| D | Tool diameter for milling and drilling, **part** diameter for turning |
| Milling feed | RPM × chip load × flutes |
| Drilling and turning feed | RPM × feed per rev |
| Radial chip thinning | chip load × 1 / √(1 − (1 − 2 × WOC / D)²), when WOC is under 50% of D |
| Circular, inside a hole | F center = F edge × (D hole − D tool) / D hole |
| Circular, around a boss | F center = F edge × (D part + D tool) / D part |
| Milling MRR | WOC × DOC × feed |
| Turning MRR | 12 × SFM × feed per rev × DOC |

RPM is capped at the machine's maximum (and the chuck's, for turning). Feed is calculated from the capped RPM.

## Data sources

Every value records its source, link, the date it was checked, and a confidence level. The site's Sources page lists them all.

| Source | Used for | Checked |
|---|---|---|
| [Harvey Tool General Machining Guidelines](https://www.harveytool.com/resources/general-machining-guidelines) | Carbide end mill surface speeds and chip loads | 2026-10-28 |
| [Tormach 1100MX](https://tormach.com/machines/mills/1100mx.html), [770MX](https://tormach.com/machines/mills/770mx.html), and [8L](https://tormach.com/support/lathe/8l-lathe-technical-specifications) spec pages | Machine presets | 2026-10-28 |

Numbers from other feeds and speeds websites are never used, and nothing is guessed: if a source doesn't give a value, it stays blank.

## Roadmap

- [x] Core formulas with tests
- [x] Material data with cited sources
- [x] Flask web app with live results
- [x] Machine presets, saved machines, horsepower check
- [x] Lathe constant surface speed (G96/G50), threading, circular interpolation
- [x] Inch/metric toggle, dark mode, mobile layout, warnings
- [x] Favorites, copy-to-setup-sheet, formula reference, data sources page, bad-number reports
- [x] Deployment setup
- [ ] Drilling and turning data, Haas and Fanuc presets, unit power for the horsepower check
- [ ] Shop-verified data from real test cuts

## Disclaimer

These are starting values only. Adjust them for your machine, setup, and rigidity.

## Author

Christopher Haynes, CNC machinist and computer science student.
