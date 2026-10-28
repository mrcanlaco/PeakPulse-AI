import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import duckdb
import typer

from dao_vang.config.settings import AppSettings
from dao_vang.data.binance_listing import (
    DEFAULT_HISTORY_PATH as _LISTING_HISTORY_PATH,
)
from dao_vang.data.binance_listing import (
    get_latest_snapshot,
    load_history,
    run_daily_scan,
)
from dao_vang.data.collectors.binance_client import BinanceClient
from dao_vang.data.collectors.klines import KlinesCollector
from dao_vang.data.daily_collection import collect_derivatives
from dao_vang.data.storage.duckdb import DuckDBQueryLayer
from dao_vang.execution.cli import app as execution_tools_app
from dao_vang.experiments.artifacts import ArtifactRegistry
from dao_vang.experiments.forward_test import (
    freeze_model,
    list_frozen_models,
)
from dao_vang.experiments.self_learning import run_self_learning
from dao_vang.features.builder import build_features
from dao_vang.labels.engine_v2 import DistributionLabelEngineV2
from dao_vang.labels.specs.distribution_short_v2 import specs as label_specs
from dao_vang.reports.generator import generate_markdown_report
from dao_vang.scanner.instance_lock import ScannerAlreadyRunning, ScannerInstanceLock

app = typer.Typer(help="Đảo Vàng CLI")

data_app = typer.Typer(help="Data collection and normalization commands")
labels_app = typer.Typer(help="Labeling commands")
features_app = typer.Typer(help="Feature generation commands")
experiment_app = typer.Typer(help="Experiment and training commands")
report_app = typer.Typer(help="Reporting commands")
scanner_app = typer.Typer(help="24/7 scanner + Telegram alerts (post-MVP, ADR 0001)")
backtest_app = typer.Typer(help="Historical Data Lake Backtest & Validation")
alpha_lab_app = typer.Typer(
    help="Alpha Quality Lab — Signal Intelligence & Meta-Labeling commands"
)
system_app = typer.Typer(
    help="System management, update, and auto-updater commands"
)
execution_app = typer.Typer(
    help="Execution Engine commands (Binance Testnet paper-trading)"
)

app.add_typer(data_app, name="data")
app.add_typer(labels_app, name="labels")
app.add_typer(features_app, name="features")
app.add_typer(experiment_app, name="experiment")
app.add_typer(backtest_app, name="backtest")
app.add_typer(report_app, name="report")
app.add_typer(scanner_app, name="scanner")
app.add_typer(alpha_lab_app, name="alpha-lab")
app.add_typer(system_app, name="system")
app.add_typer(execution_app, name="execution")
execution_app.add_typer(execution_tools_app, name="tools")


@data_app.command("collect")
def data_collect(
    start_timestamp: float,
    end_timestamp: float,
    run_id: str = "manual_run",
) -> None:
    """Collect klines data from Binance."""
    settings = AppSettings()
    client = BinanceClient()
    collector = KlinesCollector(client, settings)

    start_dt = datetime.fromtimestamp(start_timestamp, tz=timezone.utc)
    end_dt = datetime.fromtimestamp(end_timestamp, tz=timezone.utc)

    manifest = collector.collect(start_dt, end_dt, run_id)
    typer.echo(f"Collected data with manifest status: {manifest.status}")


@data_app.command("normalize")
def data_normalize() -> None:
    """Normalize raw data (placeholder)."""
    typer.echo("Normalization not fully exposed via CLI yet.")


@data_app.command("listing-scan")
def data_listing_scan(
    history_path: str = str(_LISTING_HISTORY_PATH),
    max_days: int = 365,
) -> None:
    """Scan Binance Spot/Futures listing counts and append to daily history.

    Fetches exchangeInfo from Spot, USD-M and COIN-M futures, counts coins/
    symbols currently TRADING, and appends a snapshot to the history JSON
    (overwriting any same-day entry). Designed to run once per day via cron /
    Task Scheduler.

    Examples::

        dao-vang data listing-scan
        dao-vang data listing-scan --history-path data/binance_listing_history.json
    """
    path = Path(history_path)
    snapshot = run_daily_scan(path, max_days=max_days)
    if not snapshot:
        typer.echo("Failed to fetch listing stats from Binance.", err=True)
        raise typer.Exit(code=1)

    typer.echo(f"Listing scan saved -> {path}")
    typer.echo(f"  Date:        {snapshot['date']}")
    typer.echo(f"  Fetched at:  {snapshot['fetched_at']}")
    typer.echo(f"  Spot:        {snapshot['spot_coins']} coins ({snapshot['spot_symbols']} symbols)")
    typer.echo(f"  USD-M Fut:   {snapshot['usdm_coins']} coins ({snapshot['usdm_symbols']} symbols)")
    typer.echo(f"  COIN-M Fut:  {snapshot['coinm_coins']} coins ({snapshot['coinm_symbols']} symbols)")
    typer.echo(f"  Futures all:{snapshot['futures_coins']} coins")
    typer.echo(f"  Binance all:{snapshot['all_coins']} coins")

    history = load_history(path)
    typer.echo(f"  History:     {len(history)} days (file: {path})")


@data_app.command("listing-history")
def data_listing_history(
    history_path: str = str(_LISTING_HISTORY_PATH),
    n: int = 10,
) -> None:
    """Show the most recent N listing snapshots from history."""
    path = Path(history_path)
    history = load_history(path)
    if not history:
        typer.echo(f"No history found at {path}. Run `dao-vang data listing-scan` first.")
        raise typer.Exit(code=1)

    latest = get_latest_snapshot(path)
    typer.echo(f"History: {len(history)} snapshots at {path}")
    typer.echo(f"Latest:  {latest.get('date', '?')} - Spot={latest.get('spot_coins')} "
               f"USD-M={latest.get('usdm_coins')} All={latest.get('all_coins')}")
    typer.echo("")
    typer.echo(f"Last {n} snapshots (newest first):")
    typer.echo(f"  {'Date':<12} {'Spot':>6} {'USD-M':>7} {'COIN-M':>7} {'Fut':>6} {'All':>6}")
    for s in reversed(history[-n:]):
        typer.echo(
            f"  {s.get('date', '?'):<12} {s.get('spot_coins', 0):>6} "
            f"{s.get('usdm_coins', 0):>7} {s.get('coinm_coins', 0):>7} "
            f"{s.get('futures_coins', 0):>6} {s.get('all_coins', 0):>6}"
        )


@data_app.command("collect-derivatives")
def data_collect_derivatives(
    symbols: str = typer.Argument(
        ..., help="Comma-separated USD-M futures symbols, e.g. BTCUSDT,ETHUSDT"
    ),
    hours_back: int = typer.Option(
        24, "--hours-back", "-h", help="Hours of history to fetch"
    ),
    run_id: str = typer.Option("", "--run-id", "-r", help="Optional run ID"),
) -> None:
    """Collect funding, OI, taker and ratio data for a list of symbols.

    Designed for daily cron jobs to keep OI/taker/ratio features from being
    mostly null. Example::

        dao-vang data collect-derivatives BTCUSDT,ETHUSDT,SOLUSDT --hours-back 24
    """
    settings = AppSettings()
    symbol_list = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    if not symbol_list:
        typer.echo("No symbols provided.", err=True)
        raise typer.Exit(code=1)

    summary = collect_derivatives(
        symbols=symbol_list,
        settings=settings,
        hours_back=hours_back,
        run_id=run_id or None,
    )

    typer.echo(f"Daily derivatives collection: {summary['run_id']}")
    typer.echo(f"  Symbols: {', '.join(summary['symbols'])}")
    typer.echo(f"  Range: {summary['range_start'][:19]} -> {summary['range_end'][:19]}")
    typer.echo(f"  Total rows raw: {summary['total_rows_raw']}")
    typer.echo(f"  Failures: {len(summary['failures'])}")
    for failure in summary["failures"]:
        typer.echo(
            f"    FAIL {failure['symbol']}/{failure['data_type']}: {failure['error']}"
        )


@labels_app.command("generate")
def label_generate(
    db_path: str,
    source_table: str,
    horizon_hours: int = typer.Option(24, "--horizon-hours", min=6, max=24),
    output_table: str = typer.Option("labels", "--output"),
) -> None:
    """Generate deterministic distribution_short_v2 labels (20%/24h)."""
    conn = duckdb.connect(db_path)
    if horizon_hours not in label_specs:
        raise typer.BadParameter("distribution_short_v2 supports only 24h")
    DistributionLabelEngineV2(label_specs[horizon_hours]).compute_all_to_table(
        conn, source_table, output_table
    )
    count = conn.execute(f"SELECT count(*) FROM {output_table}").fetchone()[0]
    typer.echo(f"Generated {count} {horizon_hours}h labels in {output_table}.")
    conn.close()


@labels_app.command("materialize")
def label_materialize(
    db_path: str = typer.Option(
        "data/dev.duckdb", "--db", help="Path to DuckDB file"
    ),
    source_table: str = typer.Option(
        "raw_timeline", "--source", help="Input table (raw_timeline or aligned_5m)"
    ),
    output_table: str = typer.Option(
        "labels", "--output", help="Output table name"
    ),
    horizons: str = typer.Option(
        "24",
        "--horizons",
        help="Active v2 label horizon; supported value: 24",
    ),
) -> None:
    """Materialize versioned 20%/24h labels into DuckDB.

    Recomputes ALL labels from the source table by dropping and recreating
    the output table. Designed to run periodically (cron / Task Scheduler)
    to keep labels fresh — without this, the labels table goes stale and
    the scanner's self-learning feedback loop breaks.

    Example::

        dao-vang labels materialize
        dao-vang labels materialize --db data/dev.duckdb --source raw_timeline
    """
    import time as _time

    # Label materialization drops/recreates a table and must never overlap the
    # live scanner writer. Reuse the deployment lock so a scheduled label job
    # fails closed with a clear instruction instead of invalidating DuckDB.
    deployment_lock = ScannerInstanceLock(Path(db_path).resolve().parent / "scanner.lock")
    try:
        deployment_lock.acquire()
    except ScannerAlreadyRunning as exc:
        typer.echo(f"ERROR: {exc}. Stop scanner before materializing labels.", err=True)
        raise typer.Exit(code=2) from exc

    typer.echo(f"Connecting to {db_path} (read_write)...")
    try:
        conn = duckdb.connect(db_path, read_only=False)
    except Exception as exc:
        typer.echo(f"ERROR: Cannot open DB for writing: {exc}", err=True)
        typer.echo("Stop scanner daemon and retry.", err=True)
        deployment_lock.release()
        raise typer.Exit(code=1)

    exists = conn.execute(
        "SELECT count(*) FROM information_schema.tables WHERE table_name = ?",
        [output_table],
    ).fetchone()[0]
    before = conn.execute(
        f"SELECT max(signal_time), count(*) FROM {output_table}"
    ).fetchone() if exists else (None, 0)
    typer.echo(f"Labels BEFORE: max={before[0]}, rows={before[1]}")

    src = conn.execute(
        f"SELECT max(feature_time), count(*) FROM {source_table}"
    ).fetchone()
    typer.echo(f"{source_table}: max={src[0]}, rows={src[1]}")

    typer.echo(f"\nMaterializing labels from {source_table} -> {output_table}...")
    t0 = _time.time()
    try:
        selected_horizons = tuple(
            sorted({int(value.strip()) for value in horizons.split(",") if value.strip()})
        )
    except ValueError as exc:
        raise typer.BadParameter("horizons must be 24 for distribution_short_v2") from exc
    if not selected_horizons or any(value not in label_specs for value in selected_horizons):
        raise typer.BadParameter("distribution_short_v2 supports only the 24h horizon")
    DistributionLabelEngineV2(label_specs[selected_horizons[0]]).compute_all_horizons_to_table(
        conn, source_table, output_table, horizons=selected_horizons
    )
    elapsed = _time.time() - t0

    typer.echo(f"\nDone in {elapsed:.1f}s")
    n_total, n_positive, n_excluded = conn.execute(
        f"SELECT count(*), count(*) FILTER (WHERE label_value = 1), "
        f"count(*) FILTER (WHERE label_value IS NULL) FROM {output_table}"
    ).fetchone()
    typer.echo(f"  horizons:   {','.join(str(value) for value in selected_horizons)}")
    typer.echo(f"  n_total:    {n_total}")
    typer.echo(f"  n_positive: {n_positive}")
    typer.echo(f"  n_excluded: {n_excluded}")

    after = conn.execute(
        f"SELECT max(signal_time), count(*) FROM {output_table}"
    ).fetchone()
    typer.echo(f"\nLabels AFTER: max={after[0]}, rows={after[1]}")

    conn.close()
    deployment_lock.release()
    typer.echo("Label materialization complete.")


@features_app.command("generate")
def feature_generate(
    db_path: str,
    source_table: str,
    target_table: str,
) -> None:
    """Generate features from normalized data."""
    db = DuckDBQueryLayer(db_path)
    build_features(db, source_table, target_table)
    typer.echo(f"Generated features into {target_table}")


@experiment_app.command("run")
def experiment_run(
    hypothesis_id: str,
    baseline_model: str,
    dataset_version: str,
    label_version: str,
    feature_set_version: str,
    split_version: str,
    seed: int,
    metrics: str = "precision,recall",
    artifact_dir: str = "./artifacts",
) -> None:
    """Run an experiment and save to artifact registry."""
    from dao_vang.experiments.runner import ExperimentConfig, run_experiment

    config = ExperimentConfig(
        hypothesis_id=hypothesis_id,
        baseline_model=baseline_model,
        dataset_version=dataset_version,
        label_version=label_version,
        feature_set_version=feature_set_version,
        split_version=split_version,
        seed=seed,
        metrics=metrics.split(","),
    )
    result = run_experiment(config)

    registry = ArtifactRegistry(Path(artifact_dir))
    artifact_id = registry.save_experiment(result)

    typer.echo(f"Experiment completed. Artifact ID: {artifact_id}")


@experiment_app.command("freeze")
def experiment_freeze(
    db_path: str,
    artifact_dir: str = "./artifacts",
    hypothesis_id: str = "forward_test",
    dataset_version: str = "v1",
    label_version: str = "distribution_short_v1",
    feature_set_version: str = "features_v1",
    seed: int = 42,
    horizon_hours: int = typer.Option(
        24, "--horizon-hours", min=6, max=24,
        help="Single materialized V1 horizon to freeze (6, 12 or 24)",
    ),
) -> None:
    """Freeze a trained model for forward testing.

    Trains a LogisticRegression on ALL labeled data in the DB, tunes threshold
    on the last 20% validation window, and saves the frozen model + metadata.
    The train_cutoff is the latest feature_time in the training data — data
    after this point is forward-test data.
    """
    from sklearn.impute import SimpleImputer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import Pipeline

    if horizon_hours not in {6, 12, 24}:
        raise typer.BadParameter("horizon-hours must be one of 6, 12 or 24")

    conn = duckdb.connect(db_path, read_only=True)
    try:
        df = conn.execute(
            """
            SELECT f.*, l.label_value AS is_distribution
            FROM feature_results f
            INNER JOIN labels l
                ON f.feature_time = l.signal_time AND f.symbol = l.symbol
            WHERE l.horizon_hours = ?
            """
            , [horizon_hours]).df()
    finally:
        conn.close()

    if df.empty or "is_distribution" not in df.columns:
        typer.echo("No labeled data found in DB.", err=True)
        raise typer.Exit(code=1)

    df = df.dropna(subset=["is_distribution"])
    if len(df) < 200 or df["is_distribution"].nunique() < 2:
        typer.echo(f"Insufficient data: {len(df)} rows, need ≥200 with both classes.", err=True)
        raise typer.Exit(code=1)

    df = df.sort_values("feature_time").reset_index(drop=True)
    exclude_cols = [
        "feature_time", "decision_time", "is_distribution", "quality_status",
        "symbol", "lead_time_minutes", "invalidation_time",
    ]
    feature_cols = [c for c in df.columns if c not in exclude_cols]

    # Tune threshold on last 20% validation
    val_cutoff = df["feature_time"].quantile(0.8)
    train_df = df[df["feature_time"] < val_cutoff]
    val_df = df[df["feature_time"] >= val_cutoff]

    # Serving rejects missing required inputs, so features that were not
    # materially available in the training window must not enter the frozen
    # schema.  The selection is fit on train only and recorded in metadata.
    availability = train_df[feature_cols].notna().mean()
    dropped_unavailable = [
        column for column in feature_cols if float(availability[column]) < 0.5
    ]
    feature_cols = [column for column in feature_cols if column not in dropped_unavailable]
    if not feature_cols:
        typer.echo("No features meet the train-window availability floor (50%).", err=True)
        raise typer.Exit(code=1)

    def build_estimator() -> Pipeline:
        return Pipeline(
            [
                ("imputer", SimpleImputer(strategy="median", add_indicator=True)),
                (
                    "model",
                    LogisticRegression(
                        max_iter=1000, random_state=seed, class_weight="balanced"
                    ),
                ),
            ]
        )

    model = build_estimator()
    model.fit(train_df[feature_cols], train_df["is_distribution"])

    # Threshold tuning on validation
    best_threshold, best_f1 = 0.5, 0.0
    if len(val_df) > 0 and val_df["is_distribution"].nunique() >= 2:
        y_val_prob = model.predict_proba(val_df[feature_cols])[:, 1]
        y_val = val_df["is_distribution"].values
        import numpy as np
        for thresh in np.arange(0.05, 0.95, 0.05):
            y_pred_t = (y_val_prob >= thresh).astype(int)
            tp = int(((y_pred_t == 1) & (y_val == 1)).sum())
            fp = int(((y_pred_t == 1) & (y_val == 0)).sum())
            fn = int(((y_pred_t == 0) & (y_val == 1)).sum())
            if tp + fp == 0 or tp + fn == 0:
                continue
            p = tp / (tp + fp)
            r = tp / (tp + fn)
            f1 = 2 * p * r / (p + r) if (p + r) > 0 else 0.0
            if f1 > best_f1:
                best_f1 = f1
                best_threshold = thresh

    # Retrain on ALL data with the tuned threshold
    final_model = build_estimator()
    final_model.fit(df[feature_cols], df["is_distribution"])

    train_cutoff = df["feature_time"].max()
    config = {
        "hypothesis_id": hypothesis_id,
        "dataset_version": dataset_version,
        "label_version": label_version,
        "feature_set_version": feature_set_version,
        "threshold_policy_version": "1.0",
        "seed": seed,
    }
    training_stats = {
        "train_size": len(df),
        "train_positives": int(df["is_distribution"].sum()),
        "threshold": float(best_threshold),
        "n_features": len(feature_cols),
        "dropped_unavailable_features": dropped_unavailable,
    }

    info = freeze_model(
        model=final_model,
        threshold=float(best_threshold),
        feature_cols=feature_cols,
        config=config,
        train_cutoff=train_cutoff,
        training_stats=training_stats,
        label_spec={
            "version": label_version,
            "horizon_hours": horizon_hours,
        },
        threshold_policy={
            "version": "1.0",
            "high_confidence_min_prob": float(best_threshold),
            "watch_min_prob": float(max(0.0, best_threshold * 0.75)),
        },
        artifact_dir=Path(artifact_dir),
    )
    typer.echo(f"Frozen model saved: {info.model_id}")
    typer.echo(f"  Train cutoff: {info.train_cutoff}")
    typer.echo(f"  Threshold: {info.threshold:.4f}")
    typer.echo(f"  Features: {len(info.feature_cols)}")
    typer.echo(f"  Training rows: {training_stats['train_size']} ({training_stats['train_positives']}+)")


@experiment_app.command("forward-test")
def experiment_forward_test(
    db_path: str,
    model_id: str,
    artifact_dir: str = "./artifacts",
    protocol_path: Path = typer.Option(
        Path("configs/forward_test_live_v1.json"),
        "--protocol-path",
        help="Immutable forward-test protocol JSON.",
    ),
    as_of: Optional[str] = typer.Option(
        None,
        "--as-of",
        help="Evidence cutoff timestamp; defaults to the current system time.",
    ),
    output: Optional[Path] = typer.Option(
        None,
        "--output",
        help="Optional path for the complete JSON evidence report.",
    ),
) -> None:
    """Evaluate a frozen model under a pre-declared evidence protocol.

    The command verifies the exact model/calibrator, freeze-time cutoff,
    label contract, universe policy, event grouping, and sample gates. It
    withholds all performance metrics until every gate passes.
    """
    try:
        from dao_vang.experiments.forward_evidence import (
            evaluate_forward_evidence,
            load_forward_test_protocol,
        )

        protocol = load_forward_test_protocol(protocol_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        typer.echo(
            f"Cannot load forward-test protocol {protocol_path}: {exc}",
            err=True,
        )
        raise typer.Exit(code=1) from exc

    if model_id != protocol.model_id:
        typer.echo(
            "Protocol required: requested model does not match "
            f"the locked protocol model {protocol.model_id}.",
            err=True,
        )
        raise typer.Exit(code=1)

    conn = duckdb.connect(db_path, read_only=True)
    try:
        df = conn.execute(
            """
            SELECT
                f.*,
                l.label_value AS is_distribution,
                l.horizon_hours,
                l.label_version
            FROM feature_results f
            INNER JOIN labels l
                ON f.feature_time = l.signal_time AND f.symbol = l.symbol
            WHERE l.horizon_hours = ? AND l.label_version = ?
            """,
            [protocol.label_horizon_hours, protocol.label_version],
        ).df()
    finally:
        conn.close()

    if df.empty:
        typer.echo("No data found in DB.", err=True)
        raise typer.Exit(code=1)

    result = evaluate_forward_evidence(
        model_id,
        df,
        protocol,
        artifact_dir=Path(artifact_dir),
        as_of=as_of,
    )
    serialized = json.dumps(result, ensure_ascii=False, indent=2, default=str)
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(f"{serialized}\n", encoding="utf-8")
        typer.echo(f"Evidence report: {output}")

    status = str(result["status"])
    typer.echo(f"Forward evidence: {model_id}")
    typer.echo(f"  Status: {status}")
    counts = result.get("counts") or {}
    typer.echo(
        "  Rows: "
        f"{counts.get('evaluated_rows', 0)} evaluated / "
        f"{counts.get('forward_rows', 0)} mature forward"
    )
    typer.echo(
        "  Events: "
        f"{counts.get('positive_events', 0)} positive / "
        f"{counts.get('predicted_events', 0)} predicted"
    )

    for gate_name, gate in (result.get("gates") or {}).items():
        marker = "PASS" if gate.get("passed") else "WAIT"
        actual = gate.get("actual")
        required = gate.get("required")
        detail = (
            f" ({actual}/{required})"
            if actual is not None and required is not None
            else ""
        )
        typer.echo(f"  [{marker}] {gate_name}{detail}")

    metrics = result.get("metrics")
    if status == "ok" and isinstance(metrics, dict):
        typer.echo(f"  Event precision: {metrics['event_precision']:.4f}")
        typer.echo(f"  Event recall: {metrics['event_recall']:.4f}")
        typer.echo(f"  Row precision: {metrics['row_precision']:.4f}")
        typer.echo(f"  Row recall: {metrics['row_recall']:.4f}")
        typer.echo(f"  Brier: {metrics['brier']:.4f}")
        return

    typer.echo(str(result.get("message") or status), err=status != "insufficient_evidence")
    if status != "insufficient_evidence":
        raise typer.Exit(code=1)


@experiment_app.command("frozen-list")
def experiment_frozen_list(
    artifact_dir: str = "./artifacts",
) -> None:
    """List all frozen models."""
    models = list_frozen_models(Path(artifact_dir))
    if not models:
        typer.echo("No frozen models found.")
        return
    for m in models:
        typer.echo(f"  {m.model_id}  cutoff={m.train_cutoff[:19]}  thresh={m.threshold:.4f}  features={len(m.feature_cols)}")


@experiment_app.command("train-lgbm")
def experiment_train_lgbm(
    horizon: int = typer.Option(24, "--horizon", help="Prediction horizon in hours"),
    data_dir: Path = typer.Option(Path("data"), "--data-dir", help="Data directory"),
    output_dir: Path = typer.Option(Path("artifacts"), "--output-dir", help="Artifacts directory"),
):
    """Train and freeze a LightGBM model for the frozen bundle."""
    from dao_vang.experiments.runner import train_lgbm_experiment
    train_lgbm_experiment(horizon_hours=horizon, data_dir=data_dir, output_dir=output_dir)
    typer.echo(f"LightGBM training completed and model frozen to {output_dir}")

@experiment_app.command("self-learn")
def experiment_self_learn(
    config: str = typer.Option("", "--config", "-c", help="Path to YAML config"),
    db_path: str = typer.Option("", "--db-path", help="Override self-learning DB path"),
    artifact_dir: str = typer.Option("", "--artifact-dir", help="Override artifact directory"),
    champion_model_id: str = typer.Option(
        "", "--champion-model-id", help="Model to compare against"
    ),
    force: bool = typer.Option(
        False,
        "--force",
        help="Run when the outcome threshold has not increased (data gates still apply)",
    ),
) -> None:
    """Train and evaluate one guarded challenger from materialized outcomes.

    The command never promotes a model or changes scanner.frozen_model_id.
    It is safe to run repeatedly; the self-learning state file prevents a
    duplicate run when no new outcomes have arrived.
    """

    settings = AppSettings.from_yaml(Path(config)) if config else AppSettings()
    champion = champion_model_id or settings.scanner.frozen_model_id
    if not champion:
        typer.echo(
            "ERROR: champion model is not set. Pass --champion-model-id or "
            "configure scanner.frozen_model_id.",
            err=True,
        )
        raise typer.Exit(code=1)

    result = run_self_learning(
        db_path=db_path or settings.scanner.db_path,
        artifact_dir=artifact_dir or settings.scanner.artifact_dir,
        champion_model_id=champion,
        state_path=settings.self_learning.state_path,
        report_dir=settings.self_learning.report_dir,
        min_training_outcomes=settings.self_learning.min_training_outcomes,
        min_new_outcomes=settings.self_learning.min_new_outcomes,
        min_positive_events=settings.self_learning.min_positive_events,
        min_precision_improvement=settings.self_learning.min_precision_improvement,
        max_recall_regression=settings.self_learning.max_recall_regression,
        max_brier_regression=settings.self_learning.max_brier_regression,
        recent_window_days=settings.self_learning.recent_window_days,
        recent_sample_weight=settings.self_learning.recent_sample_weight,
        historical_max_rows=settings.self_learning.historical_max_rows,
        seed=settings.self_learning.seed,
        force=force,
    )
    typer.echo(f"Self-learning status: {result.get('status', 'unknown')}")
    if result.get("reason"):
        typer.echo(f"  Reason: {result['reason']}")
    readiness = result.get("readiness")
    if isinstance(readiness, dict):
        typer.echo(
            "  Outcomes: {training_outcomes} "
            "(new {new_outcomes}), positive events: {positive_events}".format(
                **readiness
            )
        )
        if "historical_outcomes" in readiness:
            typer.echo(
                "  Sources: historical {historical_outcomes}, live {live_outcomes}, "
                "recent {recent_outcomes}, recent weight x{recent_sample_weight}"
                .format(**readiness)
            )
    if result.get("challenger_model_id"):
        typer.echo(f"  Challenger: {result['challenger_model_id']}")
        typer.echo("  Promotion: NOT automatic; review the report before canary.")
    if result.get("report_path"):
        typer.echo(f"  Report: {result['report_path']}")
    elif result.get("last_report_path"):
        typer.echo(f"  Report: {result['last_report_path']}")


@report_app.command("generate")
def report_generate(
    artifact_id: str,
    artifact_dir: str,
    output_file: str,
) -> None:
    """Generate markdown report from an artifact ID."""
    registry = ArtifactRegistry(Path(artifact_dir))
    try:
        artifact = registry.load_experiment(artifact_id)
    except FileNotFoundError:
        typer.echo(f"Artifact {artifact_id} not found in {artifact_dir}", err=True)
        raise typer.Exit(code=1)

    md = generate_markdown_report(artifact)
    out_path = Path(output_file)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(md)

    typer.echo(f"Report generated at {output_file}")


@app.callback()
def main_callback() -> None:
    """Đảo Vàng - Predictive model for crypto distribution phases."""
    pass


@backtest_app.command("run")
def backtest_run(
    start: str = typer.Option("2025-01-01", "--start", "-s", help="Start date (YYYY-MM-DD)"),
    end: str = typer.Option("2025-06-30", "--end", "-e", help="End date (YYYY-MM-DD)"),
    symbols: Optional[str] = typer.Option(None, "--symbols", help="Comma-separated symbols list (e.g. BTCUSDT,ETHUSDT)"),
    horizon: int = typer.Option(12, "--horizon", "-h", help="Horizon hours for label (6, 12, 24)"),
    data_dir: str = typer.Option("D:/Quant-trading/data_lake", "--data-dir", help="Data lake directory path"),
    output_db: str = typer.Option("artifacts/backtest_results.duckdb", "--output-db", help="Output DuckDB file"),
) -> None:
    """Run full historical backtest pipeline using Quant-trading Data Lake."""
    from dao_vang.experiments.backtest_runner import (
        BacktestRunConfig,
        FullBacktestRunner,
    )

    sym_list = [s.strip().upper() for s in symbols.split(",")] if symbols else None
    master_db = Path(data_dir) / "quant_master.duckdb"

    cfg = BacktestRunConfig(
        start_date=start,
        end_date=end,
        symbols=sym_list,
        horizon_hours=horizon,
        data_lake_root=Path(data_dir),
        master_duckdb_path=master_db,
        output_db_path=Path(output_db),
    )

    typer.echo(f"🚀 Running historical backtest from {start} to {end} on {symbols or 'all symbols'}...")
    runner = FullBacktestRunner(cfg)
    results = runner.run()

    typer.echo("\n" + "=" * 65)
    typer.echo("  📊 HISTORICAL BACKTEST RESULTS SUMMARY")
    typer.echo("=" * 65)
    typer.echo(f"  • Date Range      : {results['start_date']} → {results['end_date']}")
    typer.echo(f"  • Total Samples   : {results['total_samples']:,}")
    typer.echo(f"  • Valid Labels    : {results['valid_labels']:,}")
    typer.echo(f"  • Positive Events : {results['positive_events']:,} ({results['positive_rate']:.2%})")
    typer.echo(f"  • Output Database : {results['output_db']}")
    typer.echo("=" * 65)


# ============================================================
# SCANNER commands (post-MVP, ADR 0001)
# ============================================================


@scanner_app.command("start")
def scanner_start(
    config: str = typer.Option(
        "", "--config", "-c", help="Path to YAML config (optional)"
    ),
) -> None:
    """Start the 24/7 scanner daemon.

    Polls Binance every poll_interval_minutes, scores with frozen model,
    sends Telegram alerts on CAO/TRUNG BÌNH signals.

    Requires:
    - Frozen model (run `dao-vang experiment freeze` first).
    - Telegram bot token + chat ID (see docs/TELEGRAM_SETUP.md).
    - scanner.frozen_model_id set in config or env.

    Press Ctrl+C to stop gracefully.
    """
    from dao_vang.scanner.daemon import ScannerDaemon
    from dao_vang.scanner.instance_lock import ScannerAlreadyRunning

    if config:
        settings = AppSettings.from_yaml(Path(config))
    else:
        settings = AppSettings()

    if not settings.scanner.frozen_model_id:
        typer.echo(
            "ERROR: scanner.frozen_model_id not set.\n"
            "Run `dao-vang experiment freeze` first, then set in config or env:\n"
            "  DAO_VANG_SCANNER__FROZEN_MODEL_ID=frozen_... dao-vang scanner start",
            err=True,
        )
        raise typer.Exit(code=1)

    if not settings.telegram.bot_token or not settings.telegram.chat_id:
        typer.echo(
            "WARNING: Telegram not configured. Alerts will be logged but not sent.\n"
            "See docs/TELEGRAM_SETUP.md for setup instructions.",
            err=True,
        )

    typer.echo(f"Starting scanner with model: {settings.scanner.frozen_model_id}")
    typer.echo(f"Poll interval: {settings.scanner.poll_interval_minutes} min")
    typer.echo(f"Max coins: {settings.scanner.max_coins}")
    typer.echo(f"Alert levels: {settings.scanner.alert_levels}")
    typer.echo("Press Ctrl+C to stop.\n")

    try:
        daemon = ScannerDaemon(settings)
    except ScannerAlreadyRunning as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    daemon.run()


@scanner_app.command("materialize-outcomes")
def scanner_materialize_outcomes(
    db_path: str = typer.Option(
        "data_live/live.duckdb", "--db", help="Shadow DuckDB file"
    ),
    source_table: str = typer.Option(
        "raw_timeline", "--source", help="Point-in-time timeline table"
    ),
    horizons: str = typer.Option(
        "6,12,24", "--horizons", help="Comma-separated horizons: 6,12,24"
    ),
) -> None:
    """Materialize expired shadow predictions without inventing outcomes.

    Stop the scanner for this command if DuckDB reports a writer lock.  Rows
    whose future horizon is incomplete remain pending and are retried later.
    """

    from dao_vang.scanner.outcomes import materialize_prediction_outcomes
    from dao_vang.scanner.scan_results_store import ScanResultStore

    try:
        selected = tuple(sorted({int(item.strip()) for item in horizons.split(",") if item.strip()}))
    except ValueError as exc:
        raise typer.BadParameter("horizons must be a comma-separated list of 6, 12, 24") from exc
    if not selected or any(item not in {6, 12, 24} for item in selected):
        raise typer.BadParameter("horizons must be a non-empty subset of 6,12,24")

    try:
        prediction_store = ScanResultStore(db_path)
        db = DuckDBQueryLayer(db_path)
        resolved = materialize_prediction_outcomes(
            prediction_store,
            db,
            timeline_table=source_table,
            horizons=selected,
        )
        stats = prediction_store.materialization_stats()
    except Exception as exc:
        typer.echo(f"BLOCKED: cannot materialize outcomes: {exc}", err=True)
        typer.echo("Stop the scanner and retry if the DuckDB file is locked.", err=True)
        raise typer.Exit(code=2) from exc

    typer.echo(f"Materialized outcomes: {resolved}")
    typer.echo(f"  predictions: {stats['predictions']}")
    typer.echo(f"  outcomes:    {stats['outcomes']}")
    typer.echo(f"  pending:     {stats['pending']}")
    typer.echo(f"  excluded:    {stats['excluded']}")


@scanner_app.command("test-telegram")
def scanner_test_telegram(
    config: str = typer.Option(
        "", "--config", "-c", help="Path to YAML config (optional)"
    ),
) -> None:
    """Send a test message to verify Telegram configuration."""
    from dao_vang.alerts.telegram import TelegramNotifier

    if config:
        settings = AppSettings.from_yaml(Path(config))
    else:
        settings = AppSettings()

    notifier = TelegramNotifier(settings.telegram)
    if not notifier.is_configured:
        typer.echo(
            "ERROR: Telegram not configured.\n"
            "Set env vars:\n"
            "  DAO_VANG_TELEGRAM__BOT_TOKEN=...\n"
            "  DAO_VANG_TELEGRAM__CHAT_ID=...\n"
            "See docs/TELEGRAM_SETUP.md for details.",
            err=True,
        )
        raise typer.Exit(code=1)

    typer.echo("Sending test message...")
    if notifier.send_test():
        typer.echo("[OK] Test message sent! Check your Telegram.")
    else:
        typer.echo("[FAIL] Failed to send. Check bot token + chat ID.", err=True)
        raise typer.Exit(code=1)


@scanner_app.command("status")
def scanner_status(
    config: str = typer.Option(
        "", "--config", "-c", help="Path to YAML config (optional)"
    ),
    days: int = typer.Option(7, "--days", "-d", help="Stats for last N days"),
) -> None:
    """Show scanner status + alert history stats."""
    from dao_vang.alerts.store import AlertStore

    if config:
        settings = AppSettings.from_yaml(Path(config))
    else:
        settings = AppSettings()

    store = AlertStore(str(settings.scanner.db_path))
    stats = store.stats(days=days)

    typer.echo(f"=== Scanner Status (last {days} days) ===")
    typer.echo(f"Total alerts:    {stats['total']}")
    typer.echo(f"Alerts judged:   {stats['n_judged']}")
    typer.echo(f"Alerts hit:      {stats['n_hit']}")
    if stats["hit_rate"] is not None:
        typer.echo(f"Hit rate:        {stats['hit_rate']:.1%}")
    else:
        typer.echo("Hit rate:        N/A (no alerts judged yet)")
    typer.echo("")
    typer.echo("By risk level:")
    for level in ["CAO", "TRUNG BÌNH", "THẤP", "RẤT THẤP"]:
        n = stats["by_risk"].get(level, 0)
        if n:
            typer.echo(f"  {level:<15} {n}")

    typer.echo("")
    typer.echo(f"Frozen model:    {settings.scanner.frozen_model_id or 'NOT SET'}")
    typer.echo(f"Poll interval:   {settings.scanner.poll_interval_minutes} min")
    typer.echo(f"Max coins:       {settings.scanner.max_coins}")
    typer.echo(f"Scan mode:       {settings.scanner.scan_mode}")
    typer.echo(f"Min change %:    {settings.scanner.min_price_change_pct}%")
    typer.echo(f"Min volume:      ${settings.scanner.min_volume_usd:,.0f}")
    typer.echo(f"Include BTC:     {settings.scanner.include_btc}")
    typer.echo(f"Exclude stable:  {settings.scanner.exclude_stablecoins}")
    typer.echo(f"Cooldown:        {settings.scanner.cooldown_minutes} min")
    typer.echo(
        f"Telegram:        "
        f"{'configured' if settings.telegram.bot_token else 'NOT SET'}"
    )

    # Watchlist count
    from dao_vang.scanner.watchlist import load_manual_watchlist
    wl = load_manual_watchlist(settings.scanner.watchlist_path)
    typer.echo(f"Watchlist:       {len(wl)} coin ({settings.scanner.watchlist_path})")


@scanner_app.command("resolve-outcomes")
def scanner_resolve_outcomes(
    config: str = typer.Option(
        "", "--config", "-c", help="Path to YAML config (optional)"
    ),
) -> None:
    """Back-fill hit/miss for alerts whose 24h horizon has completed.

    This is the self-learning feedback loop: the scanner daemon already
    calls this every cycle, but it can also be run manually (e.g. via cron
    on a machine where the daemon isn't running, or to force a refresh).
    """
    from dao_vang.alerts.store import AlertStore
    from dao_vang.data.storage.duckdb import DuckDBQueryLayer
    from dao_vang.scanner.outcomes import resolve_pending_outcomes

    settings = AppSettings.from_yaml(Path(config)) if config else AppSettings()

    store = AlertStore(str(settings.scanner.db_path))
    db = DuckDBQueryLayer(str(settings.scanner.db_path))

    pending = store.pending_outcomes()
    typer.echo(f"Pending outcomes: {len(pending)}")

    n_resolved = resolve_pending_outcomes(store, db)
    typer.echo(f"Resolved: {n_resolved}")

    stats = store.stats(days=30)
    if stats["hit_rate"] is not None:
        typer.echo(
            f"Hit rate (30d):  {stats['hit_rate']:.1%} "
            f"({stats['n_hit']}/{stats['n_judged']} judged)"
        )
    else:
        typer.echo("Hit rate (30d):  N/A — not enough judged alerts yet")


@scanner_app.command("watchdog")
def scanner_watchdog(
    config: str = typer.Option(
        "", "--config", "-c", help="Path to YAML config (optional)"
    ),
    max_staleness_minutes: int = typer.Option(
        0,
        "--max-staleness-minutes",
        help="Alert threshold; defaults to scanner.max_heartbeat_age_minutes",
    ),
    heartbeat_path: str = typer.Option(
        "",
        "--heartbeat-path",
        help=(
            "Path to scanner heartbeat file "
            "(defaults to the configured data directory)"
        ),
    ),
) -> None:
    """One-shot check: is the scanner daemon actually alive?

    Intended to be run periodically by an external scheduler (cron / Windows
    Task Scheduler / a second docker-compose service) — the daemon cannot
    reliably report its own death, so this is a separate process. Sends a
    Telegram alert and exits non-zero if the heartbeat is missing or stale.
    """
    import json as _json

    from dao_vang.alerts.telegram import TelegramNotifier

    settings = AppSettings.from_yaml(Path(config)) if config else AppSettings()
    max_staleness_minutes = (
        max_staleness_minutes or settings.scanner.max_heartbeat_age_minutes
    )
    hb_path = (
        Path(heartbeat_path)
        if heartbeat_path
        else Path(settings.paths.data_dir) / "scanner_heartbeat.json"
    )
    notifier = TelegramNotifier(settings.telegram)

    if not hb_path.exists():
        msg = f"🔴 *Scanner Watchdog* — không tìm thấy heartbeat tại `{hb_path}`. Scanner có thể chưa từng chạy hoặc đã crash."
        typer.echo(msg)
        notifier.send_message(msg)
        raise typer.Exit(code=1)

    try:
        hb = _json.loads(hb_path.read_text(encoding="utf-8"))
        hb_time = datetime.fromisoformat(hb["timestamp"])
        if hb_time.tzinfo is None:
            hb_time = hb_time.replace(tzinfo=timezone.utc)
    except Exception as exc:
        msg = f"🔴 *Scanner Watchdog* — heartbeat file lỗi/không đọc được: {exc}"
        typer.echo(msg)
        notifier.send_message(msg)
        raise typer.Exit(code=1)

    age_minutes = (datetime.now(timezone.utc) - hb_time).total_seconds() / 60.0
    if age_minutes > max_staleness_minutes or hb.get("status") != "running":
        msg = (
            f"🔴 *Scanner Watchdog* — scanner có vẻ đã dừng.\n"
            f"Heartbeat cuối: {age_minutes:.1f} phút trước "
            f"(ngưỡng {max_staleness_minutes} phút), status={hb.get('status')}."
        )
        typer.echo(msg)
        notifier.send_message(msg)
        raise typer.Exit(code=1)

    typer.echo(
        f"[OK] Scanner alive — heartbeat {age_minutes:.1f} phút trước, "
        f"cycle={hb.get('cycle')}, status={hb.get('status')}."
    )


@scanner_app.command("history")
def scanner_history(
    config: str = typer.Option(
        "", "--config", "-c", help="Path to YAML config (optional)"
    ),
    symbol: str = typer.Option("", "--symbol", "-s", help="Filter by symbol"),
    days: int = typer.Option(7, "--days", "-d", help="Last N days"),
    limit: int = typer.Option(50, "--limit", "-n", help="Max rows"),
) -> None:
    """Show recent alert history."""
    from dao_vang.alerts.store import AlertStore

    if config:
        settings = AppSettings.from_yaml(Path(config))
    else:
        settings = AppSettings()

    store = AlertStore(str(settings.scanner.db_path))
    rows = store.query(
        symbol=symbol.upper() if symbol else None,
        days=days,
        limit=limit,
    )

    if not rows:
        typer.echo("No alerts found.")
        return

    typer.echo(
        f"{'Time':<20} {'Symbol':<12} {'Risk':<14} "
        f"{'Prob':>7} {'TG':>3} {'Hit':>5}"
    )
    typer.echo("-" * 65)
    for r in rows:
        st = r["signal_time"].strftime("%Y-%m-%d %H:%M") if r["signal_time"] else "?"
        tg = "✅" if r["telegram_sent"] else "—"
        hit = "✅" if r["hit"] else "❌" if r["hit"] is False else "⏳"
        typer.echo(
            f"{st:<20} {r['symbol']:<12} {r['risk_level']:<14} "
            f"{r['probability']:>6.1%} {tg:>3} {hit:>5}"
        )


# ============================================================
# SCANNER WATCHLIST commands (post-MVP — quản lý danh sách theo dõi)
# ============================================================

watchlist_app = typer.Typer(help="Quản lý danh sách theo dõi (watchlist)")
app.add_typer(watchlist_app, name="watchlist")


@watchlist_app.command("list")
def watchlist_list(
    config: str = typer.Option(
        "", "--config", "-c", help="Path to YAML config (optional)"
    ),
) -> None:
    """Hiển thị danh sách theo dõi hiện tại."""
    from dao_vang.scanner.watchlist import load_manual_watchlist

    if config:
        settings = AppSettings.from_yaml(Path(config))
    else:
        settings = AppSettings()

    symbols = load_manual_watchlist(settings.scanner.watchlist_path)
    if not symbols:
        typer.echo(f"Danh sách theo dõi trống. ({settings.scanner.watchlist_path})")
        typer.echo("Thêm coin: dao-vang watchlist add BTCUSDT")
        return

    typer.echo(f"Danh sách theo dõi ({len(symbols)} coin):")
    typer.echo(f"  File: {settings.scanner.watchlist_path}")
    for i, sym in enumerate(symbols, 1):
        typer.echo(f"  {i:>3}. {sym}")


@watchlist_app.command("add")
def watchlist_add(
    symbol: str = typer.Argument(..., help="Mã coin, VD: BTCUSDT"),
    config: str = typer.Option(
        "", "--config", "-c", help="Path to YAML config (optional)"
    ),
) -> None:
    """Thêm coin vào danh sách theo dõi."""
    from dao_vang.scanner.watchlist import add_to_watchlist

    if config:
        settings = AppSettings.from_yaml(Path(config))
    else:
        settings = AppSettings()

    symbols = add_to_watchlist(settings.scanner.watchlist_path, symbol)
    typer.echo(f"✅ Đã thêm {symbol.upper()} vào danh sách theo dõi.")
    typer.echo(f"   Tổng số coin: {len(symbols)}")
    typer.echo(f"   File: {settings.scanner.watchlist_path}")


@watchlist_app.command("remove")
def watchlist_remove(
    symbol: str = typer.Argument(..., help="Mã coin, VD: BTCUSDT"),
    config: str = typer.Option(
        "", "--config", "-c", help="Path to YAML config (optional)"
    ),
) -> None:
    """Xóa coin khỏi danh sách theo dõi."""
    from dao_vang.scanner.watchlist import remove_from_watchlist

    if config:
        settings = AppSettings.from_yaml(Path(config))
    else:
        settings = AppSettings()

    symbols = remove_from_watchlist(settings.scanner.watchlist_path, symbol)
    typer.echo(f"✅ Đã xóa {symbol.upper()} khỏi danh sách theo dõi.")
    typer.echo(f"   Còn lại: {len(symbols)} coin")
    typer.echo(f"   File: {settings.scanner.watchlist_path}")


@watchlist_app.command("clear")
def watchlist_clear(
    config: str = typer.Option(
        "", "--config", "-c", help="Path to YAML config (optional)"
    ),
    confirm: bool = typer.Option(False, "--yes", "-y", help="Bỏ qua xác nhận"),
) -> None:
    """Xóa toàn bộ danh sách theo dõi."""
    from dao_vang.scanner.watchlist import save_manual_watchlist

    if config:
        settings = AppSettings.from_yaml(Path(config))
    else:
        settings = AppSettings()

    if not confirm:
        typer.echo("⚠️  Sẽ xóa toàn bộ danh sách theo dõi.")
        typer.echo("   Chạy lại với --yes để xác nhận.")
        raise typer.Exit(code=1)

    save_manual_watchlist(settings.scanner.watchlist_path, [])
    typer.echo("✅ Đã xóa toàn bộ danh sách theo dõi.")


@scanner_app.command("scan-list")
def scanner_scan_list(
    config: str = typer.Option(
        "", "--config", "-c", help="Path to YAML config (optional)"
    ),
    mode: str = typer.Option(
        "", "--mode", "-m",
        help="Chế độ quét: gainers/losers/volume/volatile/all (override config)",
    ),
) -> None:
    """Xem trước danh sách coin sẽ quét trong chu kỳ tiếp theo.

    Hữu ích để kiểm tra cấu hình scanner trước khi chạy thật.
    """
    from dao_vang.scanner.watchlist import preview_scan_list

    if config:
        settings = AppSettings.from_yaml(Path(config))
    else:
        settings = AppSettings()

    if mode:
        settings.scanner.scan_mode = mode

    typer.echo("=== Scan List Preview ===")
    typer.echo(f"Scan mode:        {settings.scanner.scan_mode}")
    typer.echo(f"Max coins:        {settings.scanner.max_coins}")
    typer.echo(f"Min volume (USD): ${settings.scanner.min_volume_usd:,.0f}")
    typer.echo(f"Min change %:     {settings.scanner.min_price_change_pct}%")
    typer.echo(f"Include BTC:      {settings.scanner.include_btc}")
    typer.echo(f"Exclude stable:   {settings.scanner.exclude_stablecoins}")
    typer.echo("")

    try:
        preview = preview_scan_list(settings.scanner)
    except Exception as exc:
        typer.echo(f"❌ Lỗi: {exc}", err=True)
        raise typer.Exit(code=1)

    # Manual watchlist
    manual = preview["manual_watchlist"]
    typer.echo(f"📋 Danh sách theo dõi ({len(manual)} coin):")
    if manual:
        for sym in manual:
            typer.echo(f"  • {sym}")
    else:
        typer.echo("  (trống)")
    typer.echo("")

    # Auto tickers (top 10)
    auto = preview["auto_tickers_top10"]
    typer.echo(f"📡 Top {len(auto)} coin tự động (mode={preview['scan_mode']}):")
    typer.echo(f"  {'Symbol':<14} {'Change%':>10} {'Volume (USD)':>16} {'Price':>12}")
    for d in auto:
        typer.echo(
            f"  {d['symbol']:<14} {d['change_pct']:>+9.2f}% "
            f"{d['volume_usd']:>15,.0f} {d['last_price']:>12.6f}"
        )
    typer.echo("")

    # Final list
    final = preview["final_list"]
    typer.echo(f"✅ Danh sách cuối cùng sẽ quét ({len(final)} coin):")
    for i, sym in enumerate(final, 1):
        typer.echo(f"  {i:>3}. {sym}")


# ============================================================
# ALPHA QUALITY LAB commands (Triple-Barrier, Regime & Meta-Labeling)
# ============================================================


@alpha_lab_app.command("regime")
def alpha_lab_regime(
    symbol: str = typer.Option("BTCUSDT", "--symbol", "-s", help="Mã coin cần phân tích"),
    limit: int = typer.Option(100, "--limit", "-n", help="Số nến nạp vào (mặc định 100)"),
) -> None:
    """Phân tích và nhận diện trạng thái thị trường (Market Regime) hiện tại."""
    from dao_vang.alpha_lab.regime_classifier import (
        get_current_regime,
    )
    from dao_vang.data.collectors.binance_client import BinanceClient

    client = BinanceClient()
    typer.echo(f"🔍 Đang lấy {limit} nến 1h của {symbol} từ Binance Futures...")
    try:
        klines = client.get("/fapi/v1/klines", {"symbol": symbol.upper(), "interval": "1h", "limit": limit})
        import pandas as pd

        df = pd.DataFrame(
            klines,
            columns=[
                "open_time", "open", "high", "low", "close", "volume",
                "close_time", "quote_volume", "trades", "taker_buy_base",
                "taker_buy_quote", "ignore",
            ],
        )
        df["open_time"] = pd.to_datetime(df["open_time"], unit="ms")
        df = df.set_index("open_time")
        for col in ["open", "high", "low", "close"]:
            df[col] = df[col].astype(float)

        state = get_current_regime(df)

        typer.echo("\n" + "=" * 55)
        typer.echo(f"  📊 KẾT QUẢ PHÂN TÍCH REGIME: {symbol.upper()}")
        typer.echo("=" * 55)
        typer.echo(f"  • Trạng thái thị trường : 🎯 {state.regime.value}")
        typer.echo(f"  • Chỉ số ADX (Trend)   : {state.adx:.2f}")
        typer.echo(f"  • BB Width (Vol)       : {state.bb_width:.4f}")
        typer.echo(f"  • Trend Slope (EMA)    : {state.trend_slope:+.4f}")
        typer.echo(f"  • Độ biến động ATR     : {state.atr_pct:.2%}")
        typer.echo(f"  • Cho phép lệnh Short  : {'✅ CÓ' if state.allow_short else '❌ KHÔNG (Chặn ngược trend)'}")
        typer.echo(f"  • Cho phép lệnh Long   : {'✅ CÓ' if state.allow_long else '❌ KHÔNG'}")
        typer.echo(f"  • Hệ số Rủi ro (Risk)  : {state.risk_multiplier:.1f}x")
        typer.echo("=" * 55 + "\n")
    except Exception as exc:
        typer.echo(f"❌ Lỗi khi phân tích regime: {exc}", err=True)
        raise typer.Exit(code=1)


@alpha_lab_app.command("backtest")
def alpha_lab_backtest(
    pt_mult: float = typer.Option(2.0, "--pt", help="Hệ số Take Profit theo ATR"),
    sl_mult: float = typer.Option(1.0, "--sl", help="Hệ số Stop Loss theo ATR"),
    threshold: float = typer.Option(0.60, "--threshold", "-t", help="Ngưỡng Meta-Model"),
) -> None:
    """Chạy mô phỏng kiểm định Triple-Barrier & Meta-Labeling Simulator."""
    import numpy as np
    import pandas as pd

    from dao_vang.alpha_lab.alpha_backtester import AlphaBacktester

    typer.echo("🚀 Đang khởi tạo bộ giả lập Walk-Forward & Triple-Barrier Backtest...")
    np.random.seed(42)
    n_bars = 1000
    dates = pd.date_range(start="2026-01-01", periods=n_bars, freq="5min")
    prices = 100.0 * np.exp(np.cumsum(np.random.normal(0, 0.002, n_bars)))

    price_df = pd.DataFrame(
        {
            "open": prices,
            "high": prices * (1.0 + np.abs(np.random.normal(0, 0.001, n_bars))),
            "low": prices * (1.0 - np.abs(np.random.normal(0, 0.001, n_bars))),
            "close": prices,
        },
        index=dates,
    )

    sig_indices = np.sort(np.random.choice(range(50, n_bars - 150), size=60, replace=False))
    sig_dates = dates[sig_indices]
    signals_df = pd.DataFrame(
        {
            "side": [-1] * len(sig_dates),
            "primary_probability": np.random.uniform(0.65, 0.90, len(sig_dates)),
            "taker_buy_ratio": np.random.uniform(0.45, 0.65, len(sig_dates)),
            "oi_change_pct": np.random.normal(0.01, 0.03, len(sig_dates)),
        },
        index=sig_dates,
    )

    backtester = AlphaBacktester(
        pt_sl=(pt_mult, sl_mult),
        min_ret=0.005,
        fee_bps=8.0,
        meta_threshold=threshold,
    )

    res = backtester.run_simulation(prices=price_df, signals_df=signals_df, train_ratio=0.65)

    typer.echo("\n" + "=" * 65)
    typer.echo("  🔬 KẾT QUẢ SO SÁNH HIỆU SUẤT ALPHA LAB (OUT-OF-SAMPLE TEST)")
    typer.echo("=" * 65)
    typer.echo(f"  • Tổng tín hiệu kiểm thử   : {res.total_test_signals}")
    typer.echo(f"  • Lệnh được Meta-Model DUYỆT: {res.executed_signals} ({res.pass_rate:.1%})")
    typer.echo(f"  • Lệnh rác bị DROP         : {res.dropped_signals}")
    typer.echo("-" * 65)
    typer.echo(f"  • Win Rate Thô (Unfiltered) : {res.unfiltered_summary.win_rate:.1%}")
    typer.echo(f"  • Win Rate sau Lọc (Filtered): {res.filtered_summary.win_rate:.1%} (Tăng {res.winrate_improvement_pct:+.1f}%)")
    typer.echo("-" * 65)
    typer.echo(f"  • Kỳ Vọng EV Thô           : {res.unfiltered_summary.expected_value_bps:+.1f} bps")
    typer.echo(f"  • Kỳ Vọng EV sau Lọc       : {res.filtered_summary.expected_value_bps:+.1f} bps (Cải thiện {res.ev_improvement_bps:+.1f} bps)")
    typer.echo(f"  • Profit Factor Cải thiện  : {res.profit_factor_improvement:+.2f}")
    typer.echo("=" * 65 + "\n")


@alpha_lab_app.command("drift")
def alpha_lab_drift() -> None:
    """Kiểm tra độ ổn định phân phối (PSI) và giám sát Alpha Decay."""
    import numpy as np
    import pandas as pd

    from dao_vang.alpha_lab.drift_guardian import DriftGuardian

    typer.echo("🛡️  Đang chạy kiểm tra Drift Guardian...")
    np.random.seed(42)
    baseline_df = pd.DataFrame(
        {
            "atr_pct": np.random.normal(0.02, 0.005, 500),
            "taker_ratio": np.random.normal(0.50, 0.05, 500),
            "oi_delta": np.random.normal(0.0, 0.02, 500),
        }
    )
    guardian = DriftGuardian()
    guardian.set_baseline(baseline_df)

    live_df = pd.DataFrame(
        {
            "atr_pct": np.random.normal(0.021, 0.005, 200),
            "taker_ratio": np.random.normal(0.51, 0.05, 200),
            "oi_delta": np.random.normal(0.0, 0.02, 200),
        }
    )

    y_true = np.array([1, 1, 0, 1, 0, 0, 1, 0] * 20)
    y_prob = np.array([0.85, 0.80, 0.20, 0.75, 0.30, 0.25, 0.90, 0.15] * 20)

    report = guardian.evaluate_health(live_df, y_true=y_true, y_prob=y_prob)

    typer.echo("\n" + "=" * 55)
    typer.echo("  🛡️  BÁO CÁO SỨC KHỎE MÔ HÌNH (DRIFT GUARDIAN)")
    typer.echo("=" * 55)
    typer.echo(f"  • Trạng thái tổng thể : {'🟢 ' + report.status.value if report.status.value == 'HEALTHY' else '⚠️ ' + report.status.value}")
    typer.echo(f"  • Độ lệch PSI tối đa  : {report.max_psi:.4f} (Ngưỡng an toàn < 0.10)")
    for feat, psi in report.feature_psi.items():
        typer.echo(f"    - Feature '{feat:<12}': PSI = {psi:.4f}")
    if report.brier_score is not None:
        typer.echo(f"  • Brier Score (Sai số) : {report.brier_score:.4f}")
    if report.ece is not None:
        typer.echo(f"  • ECE (Lỗi hiệu chuẩn) : {report.ece:.4f}")
    typer.echo("=" * 55 + "\n")


# ==============================================================================
# SYSTEM MANAGEMENT & UPDATER COMMANDS
# ==============================================================================


@system_app.command("status")
def system_status(
    remote: str = typer.Option("origin", help="Git remote name"),
    branch: str = typer.Option("main", help="Git branch name"),
) -> None:
    """Xem trạng thái phiên bản hiện tại, commit hash và kiểm tra bản cập nhật trên GitHub."""
    from dao_vang.updater.manager import UpdateManager

    typer.echo("🔍 Đang kiểm tra trạng thái hệ thống và Git repository...")
    manager = UpdateManager()
    status = manager.check_for_updates(remote=remote, branch=branch)
    health = manager.check_system_health()

    typer.echo("\n" + "=" * 65)
    typer.echo("  🌟 TRẠNG THÁI HỆ THỐNG ĐẢO VÀNG PEAKPULSE")
    typer.echo("=" * 65)
    typer.echo(f"  • Nhánh Git hiện tại       : {status.current_branch}")
    typer.echo(f"  • Commit cục bộ (Local)    : {status.local_commit_short} - {status.local_commit_message}")
    typer.echo(f"  • Commit trên Git (Remote) : {status.remote_commit_short} - {status.remote_commit_message}")
    typer.echo(f"  • Lệch commit (Behind/Ahead): Chậm {status.commits_behind} commit | Nhanh hơn {status.commits_ahead} commit")
    typer.echo("-" * 65)
    typer.echo(f"  • DuckDB Database           : {health.get('duckdb', 'N/A')}")
    typer.echo(f"  • Scanner Daemon Heartbeat  : {health.get('scanner_heartbeat', 'N/A')}")
    typer.echo("-" * 65)

    if status.error:
        typer.secho(f"  ⚠️ Cảnh báo kiểm tra Git: {status.error}", fg=typer.colors.YELLOW)
    elif status.update_available:
        typer.secho(f"  🚀 Có bản cập nhật mới ({status.commits_behind} commit) trên GitHub!", fg=typer.colors.GREEN, bold=True)
        typer.echo("     Chạy lệnh 'dao-vang system update' để cập nhật ngay.")
    else:
        typer.secho("  ✅ Hệ thống đang ở phiên bản mới nhất.", fg=typer.colors.GREEN)
    typer.echo("=" * 65 + "\n")


@system_app.command("update")
def system_update(
    check_only: bool = typer.Option(False, "--check-only", help="Chỉ kiểm tra cập nhật mà không thực hiện kéo code"),
    force: bool = typer.Option(False, "--force", help="Bắt buộc cập nhật và tự động stash các thay đổi cục bộ"),
    no_restart: bool = typer.Option(False, "--no-restart", help="Không tự động khởi động lại dịch vụ"),
    no_frontend: bool = typer.Option(False, "--no-frontend", help="Không tự động build lại giao diện frontend"),
    remote_deploy: bool = typer.Option(False, "--remote-deploy", help="Đồng thời cập nhật server Ubuntu MSI từ xa"),
    remote: str = typer.Option("origin", "--remote", help="Tên git remote"),
    branch: str = typer.Option("main", "--branch", help="Tên git branch"),
) -> None:
    """Cập nhật hệ thống Đảo Vàng lên phiên bản mới nhất từ GitHub."""
    from dao_vang.updater.manager import UpdateManager

    manager = UpdateManager()

    if check_only:
        typer.echo(f"🔍 Đang kiểm tra bản cập nhật mới từ {remote}/{branch}...")
        status = manager.check_for_updates(remote=remote, branch=branch)
        if status.update_available:
            typer.secho(
                f"🚀 Phát hiện {status.commits_behind} commit mới trên GitHub ({status.remote_commit_short}):",
                fg=typer.colors.GREEN,
                bold=True,
            )
            for c in status.new_commits:
                typer.echo(f"   • [{c['short_hash']}] {c['message']} ({c['author']})")
        else:
            typer.secho("✅ Hệ thống đã ở phiên bản mới nhất.", fg=typer.colors.GREEN)
        return

    typer.echo("🚀 Bắt đầu quá trình cập nhật Đảo Vàng PeakPulse...")
    res = manager.apply_update(
        force=force,
        restart_services=not no_restart,
        rebuild_frontend=not no_frontend,
        notify_telegram=True,
        remote_deploy=remote_deploy,
    )

    if res.success:
        typer.secho(f"\n✅ {res.message}", fg=typer.colors.GREEN, bold=True)
    else:
        typer.secho(f"\n❌ {res.message}", fg=typer.colors.RED, bold=True)
        if res.error:
            typer.secho(f"   Chi tiết: {res.error}", fg=typer.colors.RED)
        raise typer.Exit(code=1)


@system_app.command("auto-updater")
def system_auto_updater(
    interval: int | None = typer.Option(
        None, "--interval", "-i", help="Chu kỳ kiểm tra GitHub (tính theo phút, mặc định theo cấu hình)"
    ),
) -> None:
    """Khởi chạy daemon giám sát GitHub 24/7 và tự động cập nhật hệ thống khi có bản mới."""
    from dao_vang.updater.auto_updater import run_auto_updater

    run_auto_updater(interval_minutes=interval)


# ==============================================================================
# EXECUTION ENGINE COMMANDS (ISOLATED AUTO-TRADING)
# ==============================================================================


@execution_app.command("start")
def execution_start(
    config: str = typer.Option(
        None,
        "--config",
        "-c",
        help="Path to YAML config file (default: configs/dev.yaml or env vars)",
    ),
) -> None:
    """Start the qualified-signal execution service in its configured environment."""
    from dao_vang.execution.engine import ExecutionEngine

    settings = AppSettings.from_yaml(Path(config)) if config else AppSettings()
    db_path = Path(settings.scanner.db_path)
    engine = ExecutionEngine(settings, db_path)
    typer.echo(f"Starting ExecutionEngine (db: {db_path}, environment={engine.settings.environment})...")
    engine.run_loop()


@execution_app.command("poll")
def execution_poll(
    config: str = typer.Option(
        None,
        "--config",
        "-c",
        help="Path to YAML config file (default: configs/dev.yaml or env vars)",
    ),
) -> None:
    """Reconcile account and process qualified signals once."""
    from dao_vang.execution.engine import ExecutionEngine

    settings = AppSettings.from_yaml(Path(config)) if config else AppSettings()
    db_path = Path(settings.scanner.db_path)
    engine = ExecutionEngine(settings, db_path)
    engine.connect()
    try:
        engine.poll_signals()
        typer.echo("ExecutionEngine one-shot poll complete.")
    finally:
        if getattr(engine, "_db_conn", None):
            engine._db_conn.close()
        if getattr(engine, "_exec_conn", None):
            engine._exec_conn.close()


@app.command("fibo-scan")
def fibo_scan_command(
    watch: bool = typer.Option(
        False,
        "--watch",
        "-w",
        help="Run continuously in a loop to scan and dispatch qualified Short signals to Telegram",
    ),
    interval_seconds: int = typer.Option(
        300,
        "--interval-seconds",
        help="Scan interval in seconds when --watch is enabled (default: 300s)",
    ),
    config: str = typer.Option(
        "",
        "--config",
        "-c",
        help="Path to YAML config file (optional)",
    ),
    symbols: str = typer.Option(
        "",
        "--symbols",
        "-s",
        help="Comma-separated list of symbols (optional)",
    ),
) -> None:
    """Chạy 1 chu kỳ quét nhánh Xác Nhận Đảo Chiều & Fibonacci Short (H4/D1 -> H1)."""
    from dao_vang.fibo_short.scanner_lane import run_cycle as run_fibo_cycle

    settings = AppSettings.from_yaml(Path(config)) if config else AppSettings()
    sym_list = [s.strip().upper() for s in symbols.split(",") if s.strip()] if symbols else None
    import time as _time
    while True:
        result = run_fibo_cycle(settings, symbols=sym_list)
        typer.echo(
            f"Fibo Short Scan hoàn tất: {result.get('total_signals', 0)} tín hiệu "
            f"(FIRED={result.get('fired_count', 0)}, ĐẠT_CHUẨN_SHORT={result.get('qualified_fired_count', 0)}, "
            f"TELEGRAM_SENT={result.get('telegram_sent_this_cycle', 0)}, "
            f"ARMED={result.get('armed_count', 0)}, WATCHING={result.get('watching_count', 0)})"
        )
        if not watch:
            break
        _time.sleep(max(30, int(interval_seconds)))
    return
    if False:
        result = run_fibo_cycle(settings, symbols=sym_list)
    typer.echo(
        f"Fibo Short Scan hoàn tất: {result.get('total_signals', 0)} tín hiệu "
        f"(FIRED={result.get('fired_count', 0)}, ARMED={result.get('armed_count', 0)}, "
        f"WATCHING={result.get('watching_count', 0)})"
    )


@app.command("fibo-backtest")
def fibo_backtest_command(
    config: str = typer.Option(
        "",
        "--config",
        "-c",
        help="Path to YAML config file (optional)",
    ),
    start_utc: str = typer.Option(
        "2024-01-01T00:00:00+00:00",
        "--start",
        help="In-sample start timestamp (UTC)",
    ),
    end_utc: str = typer.Option(
        "2025-12-31T23:59:59+00:00",
        "--end",
        help="In-sample end timestamp (UTC, must be <= 2025-12-31T23:59:59+00:00 to preserve 2026+ OOS)",
    ),
) -> None:
    """Chạy Backtest In-Sample (tới hết 2025, giữ nguyên 2026 làm OOS) cho nhánh Fibo Trend Short."""
    from dao_vang.fibo_short.backtest import run_in_sample_backtest_2025

    settings = AppSettings.from_yaml(Path(config)) if config else AppSettings()
    out_path = settings.scanner.artifact_dir / "fibo_trend_short" / "backtest_in_sample_2025.json"
    report = run_in_sample_backtest_2025(
        start_utc=start_utc,
        end_utc=end_utc,
        config=settings.fibo_trend_short,
        output_path=out_path,
    )
    overall = report["overall"]
    typer.echo(
        f"Fibo In-Sample Backtest (<= 2025-12-31) hoàn tất trên {report['symbols_count']} coin:\n"
        f"  • Tổng số lệnh:     {overall['total_trades']}\n"
        f"  • Win Rate:         {overall['win_rate_pct']}%\n"
        f"  • Tỷ lệ chạm TP1:   {overall['tp1_hit_rate_pct']}%\n"
        f"  • Tỷ lệ chạm TP2:   {overall['tp2_hit_rate_pct']}%\n"
        f"  • Profit Factor:    {overall['profit_factor']}\n"
        f"  • Tổng Net Return:  {overall['total_net_return_pct']}%\n"
        f"  • Max Drawdown:     {overall['max_drawdown_pct']}%\n"
        f"  • Đã lưu báo cáo:   {out_path}"
    )


if __name__ == "__main__":
    app()
