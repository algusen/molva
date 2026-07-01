"""CLI `molva` — транскрибация аудио/видео из терминала (стиль ffmpeg).

Режимы работы:
  client (по умолчанию)   — форвардит задачу работающему демону (тёплая модель).
  standalone (--no-daemon) — пайплайн запускается прямо в процессе.

Коды возврата:
  0  — все файлы обработаны успешно
  1  — ошибка аргументов / конфигурации
  2  — один или несколько файлов завершились с ошибкой
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click

from molva import client as daemon_client
from molva import daemon, output
from molva.config import Config
from molva.service import BadRequestError, MolvaService
from molva.transcriber.stub import StubTranscriber

SUPPORTED_FORMATS = ["txt", "srt", "vtt"]
SUPPORTED_BACKENDS = ["stub", "gigaam"]

_SUBCOMMANDS = {"daemon", "health"}


# ── утилиты ──────────────────────────────────────────────────────────────────

def _build_service(backend: str, device: str, cfg: Config) -> MolvaService:
    if backend == "stub":
        transcriber = StubTranscriber()
    elif backend == "gigaam":
        from molva.transcriber.gigaam import GigaAMTranscriber
        click.echo(f"Загружаю модель GigaAM-v3 ({cfg.model_revision}) …", err=True)
        transcriber = GigaAMTranscriber(
            device=None if device == "auto" else device,
            model_path=cfg.model_path,
            revision=cfg.model_revision,
        )
        click.echo("Модель готова.", err=True)
    else:
        raise click.BadParameter(f"неизвестный бэкенд: {backend}", param_hint="--backend")

    return MolvaService(
        transcriber=transcriber,
        backend=backend,
        notify=cfg.notify,
        clipboard=cfg.clipboard,
    )


def _load_config_with_overrides(backend: str, language: str, revision: str) -> Config:
    import os
    from dataclasses import replace

    from molva.config import load_config

    cfg = load_config()
    overrides: dict = {}
    if "MOLVA_BACKEND" not in os.environ:
        overrides["backend"] = backend
    if "MOLVA_LANGUAGE" not in os.environ:
        overrides["default_language"] = language
    if "MOLVA_MODEL_REVISION" not in os.environ:
        overrides["model_revision"] = revision
    return replace(cfg, **overrides)


def _print_summary(source: Path, written: list[str], duration: float, verbose: bool) -> None:
    names = ", ".join(Path(p).name for p in written) if written else "(нет выходных файлов)"
    click.echo(f"✓ {source.name} [{duration:.1f}с] → {names}")
    if verbose:
        for p in written:
            click.echo(f"  {p}")


# ── главная команда ───────────────────────────────────────────────────────────

@click.command(
    context_settings={"help_option_names": ["-h", "--help"]},
    no_args_is_help=False,
)
@click.argument("inputs", nargs=-1, required=False)
@click.option("-f", "--format", "formats", multiple=True,
              type=click.Choice(SUPPORTED_FORMATS, case_sensitive=False),
              help="Формат вывода (можно повторять). По умолчанию: txt.")
@click.option("-o", "--output", "output_path", default=None, metavar="PATH",
              help="Файл или директория вывода. По умолчанию: sidecar рядом с исходником.")
@click.option("-l", "--lang", "language", default="ru", show_default=True,
              help="Язык транскрибации.")
@click.option("--backend", default="stub", show_default=True,
              type=click.Choice(SUPPORTED_BACKENDS, case_sensitive=False),
              help="Движок: stub (тест) или gigaam (реальная модель).")
@click.option("--device", default="auto", show_default=True,
              type=click.Choice(["auto", "cpu", "mps"], case_sensitive=False),
              help="Устройство инференса.")
@click.option("--revision", default="e2e_rnnt", show_default=True,
              help="Ревизия модели GigaAM-v3.")
@click.option("--vad/--no-vad", default=True, show_default=True,
              help="Нарезка по тишине (silero-vad).")
@click.option("--stdout", "to_stdout", is_flag=True,
              help="Печатать транскрипцию в stdout (для pipe), не писать файл.")
@click.option("--json", "to_json", is_flag=True,
              help="Машиночитаемый JSON-вывод в stdout.")
@click.option("--overwrite", is_flag=True,
              help="Перезаписывать существующие sidecar-файлы.")
@click.option("--daemon/--no-daemon", "use_daemon", default=True, show_default=True,
              help="Использовать тёплый демон если запущен (--no-daemon для standalone).")
@click.option("-v", "--verbose", is_flag=True, help="Подробный вывод.")
@click.pass_context
def main(
    ctx: click.Context,
    inputs: tuple[str, ...],
    formats: tuple[str, ...],
    output_path: str | None,
    language: str,
    backend: str,
    device: str,
    revision: str,
    vad: bool,
    to_stdout: bool,
    to_json: bool,
    overwrite: bool,
    use_daemon: bool,
    verbose: bool,
) -> None:
    """Транскрибация аудио/видео файлов.

    \b
    Примеры:
      molva record.m4a
      molva --backend gigaam -f srt -f txt lecture.mp4
      molva --stdout record.wav | pbcopy
      molva *.wav --json | jq .
      molva daemon start|stop|status
      molva health
    """
    if not inputs:
        click.echo(ctx.get_help())
        sys.exit(0)

    if inputs[0] in _SUBCOMMANDS:
        _dispatch_subcommand(inputs)
        return

    effective_formats = list(formats) if formats else ["txt"]
    cfg = _load_config_with_overrides(backend, language, revision)

    # Определяем режим: client (демон) или standalone.
    url = daemon.base_url(cfg.host, cfg.port)
    running = use_daemon and daemon.is_running()

    if running:
        if verbose:
            click.echo(f"→ режим client (демон на {url})", err=True)
        service = None
    else:
        try:
            service = _build_service(backend, device, cfg)
        except RuntimeError as exc:
            click.echo(f"molva: {exc}", err=True)
            sys.exit(1)

    errors: list[str] = []
    for input_file in inputs:
        path = Path(input_file).resolve()
        if verbose:
            click.echo(f"→ {path}", err=True)

        write_formats = effective_formats if not (to_stdout or to_json) else ["txt"]
        try:
            if running:
                result = daemon_client.transcribe(url, str(path), write_formats, language)
            else:
                result = service.transcribe(  # type: ignore[union-attr]
                    str(path), formats=write_formats, language=language, overwrite=overwrite
                )
        except FileNotFoundError:
            click.echo(f"molva: файл не найден: {path}", err=True)
            errors.append(str(path))
            continue
        except BadRequestError as exc:
            click.echo(f"molva: {exc}", err=True)
            errors.append(str(exc))
            continue
        except daemon_client.DaemonError as exc:
            click.echo(f"molva: ошибка демона: {exc}", err=True)
            errors.append(str(exc))
            continue
        except Exception as exc:  # noqa: BLE001
            click.echo(f"molva: ошибка при обработке {path.name}: {exc}", err=True)
            errors.append(str(exc))
            continue

        if to_json:
            click.echo(json.dumps({
                "source": result.source,
                "duration_sec": result.duration_sec,
                "segments": [
                    {"start": s.start, "end": s.end, "text": s.text}
                    for s in result.segments
                ],
            }, ensure_ascii=False))
        elif to_stdout:
            click.echo(output.render_txt(result.segments))
        else:
            _print_summary(path, result.outputs, result.duration_sec, verbose)

    if errors:
        sys.exit(2)


# ── подкоманды ────────────────────────────────────────────────────────────────

def _dispatch_subcommand(args: tuple[str, ...]) -> None:
    cmd = args[0]
    rest = args[1:]

    if cmd == "health":
        _cmd_health()
        return

    if cmd == "daemon":
        if not rest:
            click.echo("Использование: molva daemon start|stop|status", err=True)
            sys.exit(1)
        _cmd_daemon(rest[0])
        return

    click.echo(f"molva: неизвестная подкоманда '{cmd}'", err=True)
    sys.exit(1)


def _cmd_health() -> None:
    from molva.config import load_config
    cfg = load_config()
    url = daemon.base_url(cfg.host, cfg.port)
    try:
        data = daemon_client.health(url)
        click.echo(json.dumps(data, ensure_ascii=False, indent=2))
        sys.exit(0 if data.get("status") == "ready" else 1)
    except daemon_client.DaemonError as exc:
        click.echo(f"molva health: {exc}", err=True)
        sys.exit(1)


def _cmd_daemon(action: str) -> None:
    from molva.config import load_config
    cfg = load_config()
    url = daemon.base_url(cfg.host, cfg.port)

    if action == "status":
        st = daemon.status()
        click.echo(f"демон: {st}")
        if st == "running":
            try:
                data = daemon_client.health(url)
                click.echo(f"health: {data.get('status')}  backend: {data.get('backend')}")
            except daemon_client.DaemonError:
                click.echo("(не удалось получить /health)")
        sys.exit(0 if st == "running" else 1)

    if action == "start":
        if daemon.is_running():
            click.echo("демон уже запущен", err=True)
            sys.exit(0)
        try:
            pid = daemon.start(cfg.host, cfg.port)
        except RuntimeError as exc:
            click.echo(f"molva daemon start: {exc}", err=True)
            sys.exit(1)
        click.echo(f"Демон запущен (PID {pid}). Жду готовности…", err=True)
        ready = daemon.wait_ready(url, timeout=90.0)
        if ready:
            click.echo("Демон готов.", err=True)
            sys.exit(0)
        else:
            click.echo(
                "Демон запущен, но ещё не ответил на /health. "
                "Проверьте `molva health` через несколько секунд.",
                err=True,
            )
            sys.exit(0)

    if action == "stop":
        try:
            pid = daemon.stop()
            click.echo(f"Демон остановлен (PID {pid}).")
            sys.exit(0)
        except RuntimeError as exc:
            click.echo(f"molva daemon stop: {exc}", err=True)
            sys.exit(1)

    click.echo(f"molva daemon: неизвестное действие '{action}'", err=True)
    sys.exit(1)
