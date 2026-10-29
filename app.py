"""Flask app: calculator pages, the live results endpoint, and reports.

Run it with:  flask --app app run --debug
"""

import os

import click
from flask import (Blueprint, Flask, current_app, g, redirect, render_template,
                   request, url_for)
from jinja2 import pass_context

import calculator
import data_store
import reports
import units

bp = Blueprint("main", __name__)

TABS = [("milling", "Milling"), ("drilling", "Drilling"), ("turning", "Turning")]


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_mapping(
        DATABASE=os.path.join(app.instance_path, "data.db"),
        REPORTS_DATABASE=os.path.join(app.instance_path, "reports.db"),
        DATA_DIR=str(data_store.DATA_DIR),
    )
    if test_config:
        app.config.update(test_config)

    # Rebuild the data on every start, so CSV edits show up after a restart.
    # A bad CSV row stops the app here with the file name and line number.
    data_store.build_database(app.config["DATABASE"], app.config["DATA_DIR"])
    reports.init(app.config["REPORTS_DATABASE"])

    app.register_blueprint(bp)
    app.teardown_appcontext(_close_db)
    _register_commands(app)
    return app


# --- Per-request helpers ---------------------------------------------------

def get_db():
    if "db" not in g:
        g.db = data_store.connect(current_app.config["DATABASE"])
    return g.db


def _close_db(exception=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def current_units():
    """Units from the link, else the last choice (cookie), else inch."""
    choice = request.args.get("units") or request.cookies.get("units")
    return choice if choice in units.UNIT_SYSTEMS else units.INCH


@bp.app_context_processor
def inject_units():
    unit_system = current_units()
    return {
        "units": unit_system,
        "unit_label": lambda kind: units.label(kind, unit_system),
    }


@bp.app_template_filter("fmt")
@pass_context
def fmt_filter(context, value, kind):
    return units.fmt(value, kind, context["units"])


@bp.app_template_filter("input_value")
@pass_context
def input_value_filter(context, value, kind):
    return units.input_text(value, kind, context["units"])


@bp.after_app_request
def remember_units(response):
    choice = request.args.get("units")
    if choice in units.UNIT_SYSTEMS and request.cookies.get("units") != choice:
        response.set_cookie("units", choice, max_age=60 * 60 * 24 * 365, samesite="Lax")
    return response


@bp.after_app_request
def security_headers(response):
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")  # no embedding in other sites
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    return response


# --- Calculator ------------------------------------------------------------

@bp.route("/")
def index():
    return redirect(url_for("main.calculator_page", op="milling"))


@bp.route("/<any(milling, drilling, turning):op>")
def calculator_page(op):
    target = request.args.get("convert_to")
    if target in units.UNIT_SYSTEMS:
        new_args = calculator.convert_args(op, request.args, current_units(), target)
        return redirect(url_for("main.calculator_page", op=op, **new_args))

    operation = calculator.OPERATIONS[op]
    db = get_db()
    return render_template(
        "calculator.html",
        op=op,
        tabs=TABS,
        title=operation.title,
        machine_type=operation.machine_type,
        args=request.args,
        result=_calculate(op),
        material_groups=data_store.list_material_groups(db),
        machines=data_store.list_machines(db, operation.machine_type),
        choices=calculator.CHOICES,
    )


@bp.route("/<any(milling, drilling, turning):op>/results")
def results_partial(op):
    """Just the results panel. The page's JavaScript calls this as you type."""
    return render_template("_results.html", op=op, result=_calculate(op))


def _calculate(op):
    operation = calculator.OPERATIONS[op]
    return operation.calculate(request.args, current_units(), data_store.DataLookup(get_db()))


# --- Other pages -----------------------------------------------------------

@bp.route("/formulas")
def formulas_page():
    return render_template("formulas.html")


@bp.route("/sources")
def sources_page():
    return render_template("sources.html", sources=data_store.list_sources(get_db()))


@bp.route("/report", methods=["GET", "POST"])
def report():
    if request.method == "GET":
        return render_template("report.html", form=request.args,
                               sent=request.args.get("sent") == "1")

    form = request.form
    # Hidden field people never see. Bots fill in every field.
    if form.get("website"):
        return redirect(url_for("main.report", sent="1"))

    message = form.get("message", "").strip()
    if not message:
        return render_template("report.html", form=form,
                               error="Please say which number looks wrong."), 400

    reports.save(
        current_app.config["REPORTS_DATABASE"],
        operation=form.get("op", "")[:20],
        context=form.get("context", "")[:2000],
        message=message[:2000],
        contact=form.get("contact", "").strip()[:200],
    )
    return redirect(url_for("main.report", sent="1"))


# --- Command line ----------------------------------------------------------

def _register_commands(app):
    @app.cli.command("check-data")
    def check_data():
        """Load the CSV files and show how many rows each table has."""
        # create_app() already loaded the CSVs and would have stopped with
        # the file name and line number if a row were bad.
        conn = data_store.connect(app.config["DATABASE"])
        try:
            for table in data_store.TABLES:
                count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                click.echo(f"{table}: {count} rows")
        finally:
            conn.close()
        click.echo("All data loaded without errors.")

    @app.cli.command("reports")
    def show_reports():
        """Print the bad-number reports people have sent."""
        rows = reports.list_all(app.config["REPORTS_DATABASE"])
        if not rows:
            click.echo("No reports yet.")
            return
        for row in rows:
            click.echo(f"#{row['id']}  {row['created_at']}  [{row['operation'] or '-'}]")
            click.echo(f"  {row['message']}")
            click.echo(f"  contact: {row['contact'] or '-'}")
            click.echo(f"  inputs:  {row['context'] or '-'}\n")
