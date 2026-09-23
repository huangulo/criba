import argparse
import asyncio
import csv
import getpass
import os
import sys
import uuid

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from criba.db.connection import get_async_session_factory
from criba.db.models import (
    GroundTruth,
    HeuristicScore,
    LlmAnalysis,
    Post,
    Project,
    SystemSetting,
)

VALID_LABELS = ("organic", "coordinated", "uncertain")
CONTENT_TRUNCATE = 1000
CSV_COLUMNS = ("post_id", "source", "published_at", "composite_score", "content", "label")


async def _export(args: argparse.Namespace) -> None:
    try:
        project_id = uuid.UUID(args.project_id)
    except ValueError:
        print(f"Error: invalid UUID for --project-id: {args.project_id}", file=sys.stderr)
        sys.exit(1)

    n = args.n
    high_frac = args.high_frac
    n_high = round(n * high_frac)
    n_low = n - n_high

    session_factory = get_async_session_factory()
    async with session_factory() as session:
        base = (
            select(Post.id, Post.source, Post.published_at, HeuristicScore.composite_score, Post.content)
            .join(HeuristicScore, HeuristicScore.post_id == Post.id)
            .outerjoin(GroundTruth, GroundTruth.post_id == Post.id)
            .where(Post.project_id == project_id)
            .where(GroundTruth.post_id.is_(None))
        )

        high_q = base.order_by(HeuristicScore.composite_score.desc()).limit(n_high)
        low_q = base.order_by(HeuristicScore.composite_score.asc()).limit(n_low)

        union_q = high_q.union(low_q).subquery()
        rows = (await session.execute(select(union_q))).fetchall()

    seen: set[uuid.UUID] = set()
    deduped = []
    for row in rows:
        if row[0] not in seen:
            seen.add(row[0])
            deduped.append(row)

    total_available = len(deduped)
    if total_available < n:
        print(f"Warning: only {total_available} eligible posts found (requested {n})", file=sys.stderr)

    n_high_actual = min(n_high, total_available)
    n_low_actual = total_available - n_high_actual

    with open(args.out, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, quoting=csv.QUOTE_MINIMAL)
        writer.writerow(CSV_COLUMNS)
        for row in deduped:
            post_id, source, published_at, composite_score, content = row
            truncated = content[:CONTENT_TRUNCATE] if content and len(content) > CONTENT_TRUNCATE else content
            writer.writerow([
                str(post_id),
                source,
                published_at.isoformat() if published_at else "",
                f"{composite_score:.4f}" if composite_score is not None else "",
                truncated or "",
                "",
            ])

    print(f"Exported {total_available} posts ({n_high_actual} high-score, {n_low_actual} low-score) → {args.out}")


async def _import(args: argparse.Namespace) -> None:
    rows_read = 0
    upserted = 0
    skipped_empty = 0
    errors: list[tuple[str, str]] = []

    session_factory = get_async_session_factory()
    async with session_factory() as session:
        with open(args.in_file, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                rows_read += 1
                raw_label = row.get("label", "").strip()
                post_id_str = row.get("post_id", "").strip()

                if not raw_label:
                    skipped_empty += 1
                    continue

                label = raw_label.lower()
                if label not in VALID_LABELS:
                    errors.append((post_id_str, f"invalid label: {raw_label}"))
                    continue

                try:
                    post_id = uuid.UUID(post_id_str)
                except ValueError:
                    errors.append((post_id_str, "invalid UUID"))
                    continue

                exists = (
                    await session.execute(select(Post.id).where(Post.id == post_id))
                ).scalar_one_or_none()
                if exists is None:
                    errors.append((post_id_str, "post not found"))
                    continue

                stmt = pg_insert(GroundTruth).values(
                    post_id=post_id,
                    label=label,
                    labeled_by="manual",
                )
                stmt = stmt.on_conflict_do_update(
                    index_elements=["post_id"],
                    set_={"label": stmt.excluded.label, "labeled_at": func.now()},
                )
                await session.execute(stmt)
                await session.commit()
                upserted += 1

    print(f"Import complete: {rows_read} rows read, {upserted} upserted, {skipped_empty} skipped (blank)")
    if errors:
        print(f"  {len(errors)} rows skipped (invalid):")
        for pid, reason in errors:
            print(f"    {pid}: {reason}")


def prf(tp: int, fp: int, fn: int) -> tuple[float, float, float]:
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
    return precision, recall, f1


def _confusion(label: str, predicted_positive: bool) -> str | None:
    if label == "coordinated":
        return "tp" if predicted_positive else "fn"
    if label == "organic":
        return "fp" if predicted_positive else "tn"
    return None


async def _run(args: argparse.Namespace) -> None:
    try:
        project_id = uuid.UUID(args.project_id)
    except ValueError:
        print(f"Error: invalid UUID for --project-id: {args.project_id}", file=sys.stderr)
        sys.exit(1)

    llm_threshold = args.llm_threshold

    session_factory = get_async_session_factory()
    async with session_factory() as session:
        project = (await session.execute(select(Project).where(Project.id == project_id))).scalar_one_or_none()
        if project is None:
            print(f"Error: project {project_id} not found", file=sys.stderr)
            sys.exit(1)
        project_name = project.name

        heuristic_threshold = args.heuristic_threshold
        if heuristic_threshold is None:
            setting = (
                await session.execute(
                    select(SystemSetting.value).where(SystemSetting.key == "heuristic_threshold")
                )
            ).scalar_one_or_none()
            heuristic_threshold = float(setting) if setting else 0.6

        labeled_rows = (
            await session.execute(
                select(
                    GroundTruth.post_id,
                    GroundTruth.label,
                    HeuristicScore.composite_score,
                    LlmAnalysis.coordination_probability,
                    Post.content,
                )
                .join(Post, Post.id == GroundTruth.post_id)
                .outerjoin(HeuristicScore, HeuristicScore.post_id == GroundTruth.post_id)
                .outerjoin(LlmAnalysis, LlmAnalysis.post_id == GroundTruth.post_id)
                .where(Post.project_id == project_id)
            )
        ).fetchall()

    n_coordinated = 0
    n_organic = 0
    n_uncertain = 0
    missing_heuristic = 0

    eligible: list[tuple[uuid.UUID, str, float, float | None, str | None]] = []
    llm_subset: list[tuple[uuid.UUID, str, float]] = []

    for post_id, label, composite, llm_prob, content in labeled_rows:
        if label == "coordinated":
            n_coordinated += 1
        elif label == "organic":
            n_organic += 1
        elif label == "uncertain":
            n_uncertain += 1
            continue

        if composite is None:
            missing_heuristic += 1
            continue

        eligible.append((post_id, label, composite, llm_prob, content))

        if llm_prob is not None:
            llm_subset.append((post_id, label, llm_prob))

    total_labeled = n_coordinated + n_organic + n_uncertain
    n_eligible = n_coordinated + n_organic

    print(f"Project: {project_name} ({project_id})")
    print(f"Labeled posts: {total_labeled}")
    print(f"  coordinated: {n_coordinated}")
    print(f"  organic:     {n_organic}")
    print(f"  uncertain:   {n_uncertain}   (excluded from metrics)")
    print(f"Eligible for metrics (coordinated + organic): {n_eligible}")
    if missing_heuristic:
        print(f"  ({missing_heuristic} labeled posts missing heuristic score — excluded)")
    if 0 < n_eligible < 20:
        print("\nWARNING: fewer than 20 eligible posts — metrics are statistically unreliable. Label more posts.")
    print()

    if n_eligible == 0:
        print("No eligible labeled posts. Nothing to evaluate.")
        return

    def _sweep(rows, threshold):
        tp = fp = fn = tn = 0
        for _, label, score in rows:
            cell = _confusion(label, score >= threshold)
            if cell == "tp":
                tp += 1
            elif cell == "fp":
                fp += 1
            elif cell == "fn":
                fn += 1
            elif cell == "tn":
                tn += 1
        return tp, fp, fn, tn

    heuristic_for_sweep = [(post_id, label, composite) for post_id, label, composite, _, _ in eligible]

    tp, fp, fn, tn = _sweep(heuristic_for_sweep, heuristic_threshold)
    p, r, f = prf(tp, fp, fn)
    print(f"Heuristic gate @ threshold {heuristic_threshold:.2f}:")
    print(f"  TP {tp}  FP {fp}  FN {fn}  TN {tn}")
    print(f"  precision {p:.3f}  recall {r:.3f}  f1 {f:.3f}")
    print()

    thresholds = [round(0.30 + i * 0.05, 2) for i in range(13)]
    print(f"{'thr':<6} {'TP':>3} {'FP':>3} {'FN':>3} {'TN':>3}   {'prec':>5} {'rec':>5} {'f1':>5}")
    best_f1 = -1.0
    best_thr = thresholds[0]
    for t in thresholds:
        tp2, fp2, fn2, tn2 = _sweep(heuristic_for_sweep, t)
        p2, r2, f2 = prf(tp2, fp2, fn2)
        print(f"{t:<6.2f} {tp2:>3} {fp2:>3} {fn2:>3} {tn2:>3}   {p2:>5.3f} {r2:>5.3f} {f2:>5.3f}")
        if f2 > best_f1:
            best_f1 = f2
            best_thr = t
    print(f"\nBest F1 at threshold {best_thr:.2f} (f1={best_f1:.3f})")
    print()

    leakage = [
        (post_id, composite, content)
        for post_id, label, composite, _, content in eligible
        if label == "coordinated" and composite < heuristic_threshold
    ]
    if leakage:
        print(f"Gate leakage — coordinated posts below threshold {heuristic_threshold:.2f} ({len(leakage)}):")
        for post_id, score, content in leakage[:25]:
            snippet = (content or "")[:80].replace("\n", " ")
            print(f"  {post_id}  score={score:.4f}  {snippet}")
        if len(leakage) > 25:
            print(f"  ... and {len(leakage) - 25} more")
    else:
        print(f"Gate leakage — coordinated posts below threshold {heuristic_threshold:.2f} (0)")
    print()

    if not llm_subset:
        print("LLM eval: no labeled posts have LLM analysis yet — skipping LLM metrics.")
    else:
        tp3, fp3, fn3, tn3 = _sweep(llm_subset, llm_threshold)
        p3, r3, f3 = prf(tp3, fp3, fn3)
        print(f"LLM coordination eval @ threshold {llm_threshold:.2f}  (n={len(llm_subset)}):")
        print(f"  TP {tp3}  FP {fp3}  FN {fn3}  TN {tn3}")
        print(f"  precision {p3:.3f}  recall {r3:.3f}  f1 {f3:.3f}")


async def _login_telegram() -> None:
    """Create a Telegram session file for the worker, interactively.

    The polling worker cannot do interactive auth (one-time login codes),
    so this command runs the send_code_request -> sign_in flow once and
    saves the session to TELEGRAM_SESSION_PATH.
    """
    from telethon import TelegramClient
    from telethon.errors import PhoneCodeInvalidError, SessionPasswordNeededError

    api_id = int(os.environ.get("TELEGRAM_API_ID", "0"))
    api_hash = os.environ.get("TELEGRAM_API_HASH", "")
    phone = os.environ.get("TELEGRAM_PHONE", "")
    session_path = os.environ.get("TELEGRAM_SESSION_PATH", "telegram_session")

    if not api_id or not api_hash:
        print("Error: TELEGRAM_API_ID and TELEGRAM_API_HASH must be set.", file=sys.stderr)
        sys.exit(1)
    if not phone:
        print("Error: TELEGRAM_PHONE must be set (international format, e.g. +573001234567).", file=sys.stderr)
        sys.exit(1)

    session_file = session_path if session_path.endswith(".session") else f"{session_path}.session"

    client = TelegramClient(session_path, api_id, api_hash)
    await client.connect()
    try:
        if await client.is_user_authorized():
            me = await client.get_me()
            print(f"Session already authorized ({getattr(me, 'username', None) or phone}); nothing to do.")
            return

        print(f"Requesting a login code for {phone} ...")
        await client.send_code_request(phone)

        code = os.environ.get("TELEGRAM_CODE", "").strip() or input("Enter the login code: ").strip()
        try:
            await client.sign_in(phone, code)
        except SessionPasswordNeededError:
            await client.sign_in(password=getpass.getpass("Two-factor password: "))
        except PhoneCodeInvalidError:
            print("Error: the login code was rejected. Wait for a fresh code and try again.", file=sys.stderr)
            sys.exit(1)

        me = await client.get_me()
        print(f"Logged in as {getattr(me, 'username', None) or phone}.")
        print(f"Session saved to {session_file}; the worker picks it up via TELEGRAM_SESSION_PATH.")
    finally:
        await client.disconnect()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="criba", description="Criba CLI")
    subparsers = parser.add_subparsers(dest="command")

    login_parser = subparsers.add_parser("login", help="Interactive login for sources that need credentials")
    login_sub = login_parser.add_subparsers(dest="login_command")

    login_sub.add_parser("telegram", help="Create the Telegram session file used by the worker")

    eval_parser = subparsers.add_parser("eval", help="Evaluation harness commands")
    eval_sub = eval_parser.add_subparsers(dest="eval_command")

    export_p = eval_sub.add_parser("export", help="Export stratified post sample for labeling")
    export_p.add_argument("--project-id", required=True, help="Project UUID to scope the sample")
    export_p.add_argument("--out", required=True, help="Output CSV path")
    export_p.add_argument("--n", type=int, default=300, help="Total posts to sample (default: 300)")
    export_p.add_argument("--high-frac", type=float, default=0.5, help="Fraction from high-score posts (default: 0.5)")

    import_p = eval_sub.add_parser("import", help="Import labeled CSV into ground_truth table")
    import_p.add_argument("--in", dest="in_file", required=True, help="Input labeled CSV path")

    run_p = eval_sub.add_parser("run", help="Run evaluation report against labeled posts")
    run_p.add_argument("--project-id", required=True, help="Project UUID to evaluate")
    run_p.add_argument("--heuristic-threshold", type=float, default=None, help="Heuristic gate threshold (default: read from system_settings, or 0.6)")
    run_p.add_argument("--llm-threshold", type=float, default=0.5, help="LLM coordination probability threshold (default: 0.5)")

    args = parser.parse_args(argv)

    if args.command == "login":
        if args.login_command == "telegram":
            asyncio.run(_login_telegram())
        else:
            login_parser.print_help()
            sys.exit(1)
    elif args.command == "eval":
        if args.eval_command == "export":
            asyncio.run(_export(args))
        elif args.eval_command == "import":
            asyncio.run(_import(args))
        elif args.eval_command == "run":
            asyncio.run(_run(args))
        else:
            eval_parser.print_help()
            sys.exit(1)
    else:
        parser.print_help()
        sys.exit(1)
