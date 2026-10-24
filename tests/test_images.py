"""Règle image commune des produits Nexus (shared/images.md, 24/10) : 1568 px / 1,15 Mpx, WebP, 500 Ko, zoom, pas de
double, échelle dite."""

from __future__ import annotations

import io
import random
from pathlib import Path

import computer_client
import mcp_server
from PIL import Image


def _ui(width: int, height: int) -> Image.Image:
    image = Image.new("RGB", (width, height), (243, 243, 243))
    for y in range(0, height, 40):
        image.paste((30, 90, 200), (20, y + 8, min(width, 420), y + 30))
    return image


def _capture(monkeypatch, image: Image.Image) -> None:
    """Capture GDI factice de la fenêtre 4242 (2560×1440 à l'écran)."""
    monkeypatch.setattr(computer_client, "ensure_default_desktop", lambda: None)
    monkeypatch.setattr(computer_client, "resolve_window", lambda hwnd=None: 4242)
    monkeypatch.setattr(computer_client, "ensure_readable", lambda hwnd: None)
    monkeypatch.setattr(computer_client.user32, "GetForegroundWindow", lambda: 1)
    monkeypatch.setattr(computer_client, "capture_window_background_gdi", lambda hwnd: image.copy())
    rect = {"left": 0, "top": 0, "width": image.width, "height": image.height}
    monkeypatch.setattr(computer_client, "get_window_rect", lambda hwnd: dict(rect))


def test_ui_capture_is_lossless_webp_within_the_common_limits(monkeypatch):
    _capture(monkeypatch, _ui(2560, 1440))
    data, meta = computer_client.capture_window_image(4242, return_meta=True)
    back = Image.open(io.BytesIO(data))
    width, height = back.size
    assert back.format == "WEBP" and max(width, height) <= 1568 and width * height <= 1_150_000
    assert width > 1280  # avant : 1280 px
    assert len(data) <= computer_client.IMAGE_LOSSLESS_BUDGET
    assert meta["scale_factor"] == round(width / 2560, 4) and meta["image_print"]


def test_noisy_capture_stays_under_the_hard_limit_with_the_same_size():
    random.seed(3)
    image = Image.frombytes("RGB", (1568, 733), random.randbytes(1568 * 733 * 3))
    data = computer_client.encode_webp(image)
    assert Image.open(io.BytesIO(data)).size == image.size  # échelle annoncée inchangée
    assert len(data) <= computer_client.IMAGE_LIMIT


def test_zoom_enlarges_the_area_without_marks(monkeypatch):
    _capture(monkeypatch, _ui(1000, 800))
    data, meta = computer_client.capture_window_image(
        4242, zoom=[0, 0, 250, 250], return_meta=True, elements_to_annotate=[{"index": 1, "box_2d": [0, 0, 100, 100]}]
    )
    assert Image.open(io.BytesIO(data)).size == (500, 400)  # 250×200 agrandi ×2
    assert meta["zoom"] == [0, 0, 250, 250] and meta["scale_x"] == meta["scale_y"] == 2.0


def test_same_screen_is_not_sent_twice_but_a_change_is(monkeypatch, tmp_path: Path):
    mcp_server._SENT_IMAGES.clear()
    shot = tmp_path / "shot.webp"
    shot.write_bytes(b"RIFFwebp")
    state = {"hwnd": 4242, "title": "T", "elements": [], "screenshot_path": str(shot), "image_print": "a",
             "image_dimensions": (1568, 882), "scale_factor": 0.6125}  # fmt: skip
    monkeypatch.setattr(computer_client, "look", lambda **kwargs: dict(state))
    first = mcp_server.computer_look(hwnd=4242)
    second = mcp_server.computer_look(hwnd=4242)
    assert isinstance(first, list) and "x image / 0.6125" in first[0]
    assert isinstance(second, str) and mcp_server.UNCHANGED_NOTE in second
    state["image_print"] = "b"
    assert isinstance(mcp_server.computer_look(hwnd=4242), list)


def test_look_text_gives_the_zoom_origin_and_scale():
    state = {"hwnd": 1, "title": "T", "elements": [], "bounds": {"width": 2000, "height": 1000},
             "image_dimensions": (1000, 500), "scale_x": 2.0, "scale_y": 1.5, "image_origin": (500.0, 250.5),
             "zoom": [250, 250, 500, 500]}  # fmt: skip
    text = computer_client.format_look(state)
    assert "x fenêtre = 500 + x image / 2.0, y fenêtre = 250.5 + y image / 1.5" in text


def test_zoom_scales_are_exact_per_axis(monkeypatch):
    # Scénario de Codex : fenêtre 1001×1000, zoom [0, 1, 1000, 2] → zone 2×1000, image 3×1568 : échelles 1,5 et 1,568.
    window = Image.new("RGB", (1001, 1000), (255, 255, 255))
    window.paste((255, 0, 0), (0, 500, 1001, 501))  # ligne rouge à y fenêtre = 500
    _capture(monkeypatch, window)
    data, meta = computer_client.capture_window_image(4242, zoom=[0, 1, 1000, 2], return_meta=True)
    image = Image.open(io.BytesIO(data)).convert("RGB")
    assert image.size == (3, 1568) and meta["image_origin"] == (1.0, 0.0)
    green = image.getchannel("G").tobytes()  # rouge : peu de vert
    rows = [y for y in range(image.height) if green[y * image.width + 1] < 128]
    y_image = sum(rows) / len(rows)
    assert abs(meta["image_origin"][1] + y_image / meta["scale_y"] - 500) <= 1.0  # avant : 238 px d'écart


def test_json_look_stays_valid_when_the_image_is_unchanged(monkeypatch, tmp_path: Path):
    import json

    mcp_server._SENT_IMAGES.clear()
    shot = tmp_path / "shot.webp"
    shot.write_bytes(b"RIFFwebp")
    state = {"hwnd": 4343, "title": "T", "elements": [], "screenshot_path": str(shot), "image_print": "z"}
    monkeypatch.setattr(computer_client, "look", lambda **kwargs: dict(state))
    first = mcp_server.computer_look(hwnd=4343, format="json")
    second = mcp_server.computer_look(hwnd=4343, format="json")
    assert isinstance(first, list) and json.loads(first[0])["status"] == "success"
    assert json.loads(second)["data"]["image"] == mcp_server.UNCHANGED_NOTE
    assert isinstance(mcp_server.computer_look(hwnd=4343, annotate=True), list)  # annotate : toujours jointe


def test_print_tells_red_from_green_of_the_same_grey():
    red = Image.new("RGB", (800, 600), (255, 0, 0))
    green = Image.new("RGB", (800, 600), (0, 130, 0))
    assert red.convert("L").tobytes() == green.convert("L").tobytes()  # même gris : l'empreinte grise les confondait
    assert computer_client.image_print(red) != computer_client.image_print(green)
