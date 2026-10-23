"""Molette Chromium par DevTools (recette B du banc commun, portée de Codex le 21/10) : preuves hors ligne, aucune
entrée réelle. Chaque refus doit arriver AVANT l'envoi."""

from __future__ import annotations

import base64
import contextlib
import hashlib
import json
import re
import socket
import struct
import threading
import time
from typing import Any

import cdp_wheel
import pytest

PORT = 9333


def page(title: str, ws: str | None = None, kind: str = "page") -> dict[str, Any]:
    return {
        "type": kind,
        "title": title,
        "webSocketDebuggerUrl": ws or f"ws://127.0.0.1:{PORT}/devtools/page/{title[:4]}",
    }


def test_port_lu_dans_la_ligne_de_commande() -> None:
    assert cdp_wheel.port_from("app.exe --remote-debugging-port=9333 --x") == 9333
    assert cdp_wheel.port_from("app.exe --remote-debugging-port 9333") == 9333
    assert cdp_wheel.port_from("app.exe --remote-debugging-port=0") is None
    assert cdp_wheel.port_from("app.exe --remote-debugging-pipe") is None
    assert cdp_wheel.port_from(None) is None


def test_port_ecoute_par_le_pid_exact_seulement() -> None:
    assert cdp_wheel.owns_port(10, [("127.0.0.1", 10)])
    assert cdp_wheel.owns_port(10, [("0.0.0.0", 10)])
    assert not cdp_wheel.owns_port(10, [("127.0.0.1", 11)])  # autre processus (parent, enfant ou étranger)
    assert not cdp_wheel.owns_port(10, [("127.0.0.1", 10), ("127.0.0.1", 11)])  # ambigu
    assert not cdp_wheel.owns_port(10, [("192.0.2.2", 10)])  # adresse non contactée
    assert not cdp_wheel.owns_port(10, [])
    # l'adresse contactée (127.0.0.1) prime : un 0.0.0.0 du bon PID ne couvre pas un 127.0.0.1 étranger
    assert not cdp_wheel.owns_port(10, [("127.0.0.1", 11), ("0.0.0.0", 10)])


def test_page_au_titre_decode_exact_et_unique() -> None:
    edge = "A & B - Profil 1 - Microsoft​ Edge"
    assert cdp_wheel.pick_page([page("A &amp; B"), page("A")], edge, PORT).endswith("/A &a")
    assert cdp_wheel.pick_page([page("Dire &quot;oui&quot; &lt;3")], 'Dire "oui" <3 - Google Chrome', PORT)
    assert cdp_wheel.pick_page([page("Editor")], "Editor", PORT)  # Electron : titre tel quel
    with pytest.raises(cdp_wheel.NotApplicable):
        cdp_wheel.pick_page([page("A")], "A & B - Microsoft Edge", PORT)  # préfixe : pas une égalité
    with pytest.raises(cdp_wheel.NotApplicable):
        cdp_wheel.pick_page([page("Doc"), page("Doc")], "Doc - Google Chrome", PORT)  # homonymes
    with pytest.raises(cdp_wheel.NotApplicable):
        cdp_wheel.pick_page([page("Autre")], "Editor", PORT)  # une seule page, autre titre : jamais acceptée
    with pytest.raises(cdp_wheel.NotApplicable):
        cdp_wheel.pick_page([page("Doc", kind="service_worker")], "Doc", PORT)
    with pytest.raises(cdp_wheel.NotApplicable):
        cdp_wheel.pick_page([page("Doc", ws="ws://127.0.0.1:9444/devtools/page/x")], "Doc", PORT)  # autre port
    with pytest.raises(cdp_wheel.NotApplicable):
        cdp_wheel.pick_page([page("Doc", ws=f"ws://198.51.100.1:{PORT}/devtools/page/x")], "Doc", PORT)  # autre hôte
    assert cdp_wheel.pick_page([page("Doc", ws=f"ws://localhost:{PORT}/p")], "Doc", PORT) == f"ws://127.0.0.1:{PORT}/p"


def test_sens_seul_le_vertical_windows_s_inverse() -> None:
    assert cdp_wheel.devtools_deltas(-1, 0) == (0, 120)  # cran vers le bas
    assert cdp_wheel.devtools_deltas(1, 0) == (0, -120)  # vers le haut
    assert cdp_wheel.devtools_deltas(0, 1) == (120, 0)  # vers la droite
    assert cdp_wheel.devtools_deltas(0, -2) == (-240, 0)  # vers la gauche, deux crans


class Page:
    """Page factice : titre, fenêtre qui le reflète (ou non), expressions de la preuve reconnues."""

    def __init__(
        self,
        title: str | None,
        shows: bool,
        changes_to: str | None = None,
        changed_before_pose: bool = False,
        window_keeps_nonce: bool = False,
        broken_restore: bool = False,
        pose_raises: bool = False,
        window_after: str | None = None,
        suffix: str = "",
    ) -> None:
        self.title, self.shows, self.changes_to, self.window = title, shows, changes_to, "Doc"
        self.changed_before_pose, self.window_keeps_nonce, self.broken_restore = (
            changed_before_pose,
            window_keeps_nonce,
            broken_restore,
        )
        self.calls: list[str] = []
        self.nonce: str | None = None
        self.pose_raises = pose_raises
        self.window_after = window_after
        self.suffix = suffix

    def evaluate(self, expression: str) -> Any:
        self.calls.append(expression)
        if expression == "document.title":
            return self.title
        if "return false; document.title = " in expression:  # pose conditionnelle
            original = json.loads(expression.split("document.title !== ", 1)[1].split(")", 1)[0])
            self.nonce = json.loads(expression.split("document.title = ", 1)[1].split(";", 1)[0])
            if self.changed_before_pose:
                self.title = "Changé"
            if self.title != original:
                return False
            self.title = self.nonce
            if self.shows:
                self.window = (self.nonce or "") + self.suffix
            if self.pose_raises:
                raise TimeoutError("réponse perdue après la pose")
            if self.changes_to:
                self.title = self.changes_to  # la page change elle-même son titre pendant la preuve
            return True
        if "return document.title !== " in expression:  # remise conditionnelle
            if self.broken_restore:
                raise ConnectionError("connexion cassée")
            original = json.loads(expression.split("document.title = ", 1)[1].split(";", 1)[0])
            if self.title == self.nonce:
                self.title = original
            if not self.window_keeps_nonce:
                # la fenêtre reflète le titre RÉEL de la page, sauf fenêtre factice qui montre autre chose
                self.window = self.window_after or (self.title or "") + self.suffix
            return self.title != self.nonce
        raise AssertionError(expression)


def run(p: Page, reconnect: Any = None) -> None:
    ticks = iter(range(10_000))
    cdp_wheel.prove(
        lambda: p.window or "", p.evaluate, reconnect, sleep=lambda _: None, clock=lambda: next(ticks) * 0.01
    )


def test_preuve_par_titre_nonce() -> None:
    ok = Page("Doc", shows=True)
    run(ok)
    assert ok.title == "Doc"  # titre d'origine remis
    absent = Page("Doc", shows=False)
    with pytest.raises(cdp_wheel.NotApplicable):
        run(absent)  # le nonce n'apparaît jamais dans CETTE fenêtre : refus
    assert absent.title == "Doc"
    unreadable = Page(None, shows=True)
    with pytest.raises(cdp_wheel.NotApplicable):
        run(unreadable)
    assert len(unreadable.calls) == 1  # rien écrit si l'origine est illisible
    moved = Page("Doc", shows=True, changes_to="Nouveau")
    run(moved)
    assert moved.title == "Nouveau"  # la page a changé son titre entre-temps : il n'est pas écrasé


def test_titre_final_de_la_page_doit_etre_celui_de_la_fenetre() -> None:
    """Relecture de Codex (19:28) : nonce absent de la fenêtre, mais titre final de la page = A et titre natif = B :
    le retour à LA page n'est pas prouvé, refus."""
    other = Page("Doc", shows=True, window_after="Autre")
    with pytest.raises(cdp_wheel.NotApplicable, match="titre final"):
        run(other)
    assert other.title == "Doc"  # titre de la page jamais écrasé


def test_habillage_exact_du_navigateur_rejoue_au_controle_final() -> None:
    """Relecture de Codex (19:36) : titre de page « Rapport », onglet B « Rapport - Personnel » : l'expression
    acceptait « Rapport - Personnel - Google Chrome » (profil facultatif réinterprété). L'habillage observé autour du
    nonce (« - Google Chrome ») est exigé tel quel."""
    run(Page("Rapport", shows=True, suffix=" - Google Chrome"))  # même onglet : accepté
    other = Page("Rapport", shows=True, suffix=" - Google Chrome", window_after="Rapport - Personnel - Google Chrome")
    with pytest.raises(cdp_wheel.NotApplicable, match="titre final"):
        run(other)
    edge = Page("Doc", shows=True, suffix=" - Profil 1 - Microsoft\u200b Edge")
    run(edge)  # habillage avec profil, observé puis rejoué exactement


def test_preuve_course_lecture_pose_refusee_sans_ecrire() -> None:
    """Relecture de Codex : titre changé entre la lecture et la pose : refus, le titre de la page n'est pas écrasé."""
    raced = Page("Doc", shows=True, changed_before_pose=True)
    with pytest.raises(cdp_wheel.NotApplicable, match="changé"):
        run(raced)
    assert raced.title == "Changé"


def test_pose_qui_leve_nettoie_et_attend_la_fenetre() -> None:
    """Relecture de Codex (19:18) : pose posée puis réponse perdue : la page est nettoyée ET le titre de la fenêtre
    relu ; revenu : refus ordinaire ; resté : refus « titre peut-être resté » (title_left)."""
    lost = Page("Doc", shows=True, pose_raises=True)
    with pytest.raises(cdp_wheel.NotApplicable) as refusal:
        run(lost)
    assert lost.title == "Doc" and lost.window == "Doc" and not getattr(refusal.value, "title_left", False)
    sticky = Page("Doc", shows=True, pose_raises=True, window_keeps_nonce=True)
    with pytest.raises(cdp_wheel.NotApplicable) as refusal:
        run(sticky)
    assert getattr(refusal.value, "title_left", False)


def test_fenetre_doit_ne_plus_montrer_le_nonce() -> None:
    """Relecture de Codex : sinon l'empreinte de l'appelant voyait le titre changé et validait un faux effet."""
    sticky = Page("Doc", shows=True, window_keeps_nonce=True)
    with pytest.raises(cdp_wheel.NotApplicable) as refusal:
        run(sticky)
    assert getattr(refusal.value, "title_left", False)


def test_remise_sur_nouvelle_connexion_puis_aveu() -> None:
    broken = Page("Doc", shows=True, broken_restore=True)
    fresh = Page("Doc", shows=True)

    def reconnect() -> Any:
        fresh.title, fresh.nonce, fresh.window = broken.title, broken.nonce, broken.window

        def evaluate(expression: str) -> Any:  # même page, autre connexion : la fenêtre suit la page
            value = fresh.evaluate(expression)
            broken.window = fresh.window
            return value

        return evaluate

    run(broken, reconnect)  # remise faite sur la nouvelle connexion
    assert fresh.title == "Doc"
    lost = Page("Doc", shows=True, broken_restore=True)
    with pytest.raises(cdp_wheel.NotApplicable) as refusal:
        run(lost, lambda: (_ for _ in ()).throw(ConnectionError("injoignable")))
    assert getattr(refusal.value, "title_left", False)  # dit explicitement : titre peut-être resté


def test_surface_regle_commune_une_seule_zone_visible() -> None:
    """Relecture de Codex (19:18) : exactement UNE zone de rendu visible dans la fenêtre, le point dedans, taille =
    round(inner × DPR) à ceil(DPR) px près ; plusieurs zones (Electron multi-vues, DevTools ancré) : refus."""
    page_surface = (100, 50, 800, 600)
    got = cdp_wheel.pick_surface([page_surface], (300, 300), (800, 600), 1.0)
    assert (got["left"], got["top"], got["gap_px"], got["dpr"]) == (100, 50, [0, 0], 1.0)
    assert cdp_wheel.pick_surface([(0, 0, 1200, 900)], (5, 5), (800, 600), 1.5)["gap_px"] == [0, 0]  # DPR 150 %
    assert cdp_wheel.pick_surface([(0, 0, 1202, 899)], (5, 5), (800, 600), 1.5)["gap_px"] == [2, -1]  # ceil(1,5) = 2
    with pytest.raises(cdp_wheel.NotApplicable):
        cdp_wheel.pick_surface([(0, 0, 1203, 900)], (5, 5), (800, 600), 1.5)  # 3 px d'écart : refus
    with pytest.raises(cdp_wheel.NotApplicable):
        cdp_wheel.pick_surface([page_surface, (300, 200, 400, 300)], (350, 250), (800, 600), 1.0)  # deux vues
    with pytest.raises(cdp_wheel.NotApplicable):
        cdp_wheel.pick_surface([page_surface, (2000, 0, 50, 50)], (300, 300), (800, 600), 1.0)  # même hors du point
    with pytest.raises(cdp_wheel.NotApplicable):
        cdp_wheel.pick_surface([page_surface], (950, 300), (800, 600), 1.0)  # point hors de la zone
    with pytest.raises(cdp_wheel.NotApplicable):
        cdp_wheel.pick_surface([], (300, 300), (800, 600), 1.0)


# --- transport : faux serveur WebSocket local (aucune page réelle)
GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


def frame(payload: bytes, opcode: int = 0x1, fin: bool = True) -> bytes:
    head = bytes([(0x80 if fin else 0) | opcode])
    n = len(payload)
    if n < 126:
        return head + bytes([n]) + payload
    return head + bytes([126]) + struct.pack(">H", n) + payload


class Server:
    """Une connexion : poignée de main (accept juste ou faux), puis le script d'octets rendu après la 1re requête."""

    def __init__(self, script: list[Any], good_accept: bool = True, redirect_to: int | None = None) -> None:
        self.sock = socket.socket()
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(1)
        self.port = self.sock.getsockname()[1]
        self.script, self.good_accept, self.redirect_to = script, good_accept, redirect_to
        self.thread = threading.Thread(target=self.serve, daemon=True)
        self.thread.start()

    def serve(self) -> None:
        conn, _ = self.sock.accept()
        with conn:
            data = b""
            while b"\r\n\r\n" not in data:
                data += conn.recv(4096)
            key = re.search(rb"Sec-WebSocket-Key: (\S+)", data, re.IGNORECASE).group(1).decode()  # type: ignore[union-attr]
            accept = base64.b64encode(hashlib.sha1((key + GUID).encode()).digest()).decode()
            if not self.good_accept:
                accept = base64.b64encode(b"faux" * 5).decode()
            if self.redirect_to is not None:
                conn.sendall(f"HTTP/1.1 302 Found\r\nLocation: ws://127.0.0.1:{self.redirect_to}/x\r\n\r\n".encode())
                time.sleep(1.0)
                return
            conn.sendall(
                (
                    "HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                    f"Sec-WebSocket-Accept: {accept}\r\n\r\n"
                ).encode()
            )
            with contextlib.suppress(OSError):
                conn.recv(4096)  # la requête CDP
                for step in self.script:
                    if isinstance(step, float):
                        time.sleep(step)
                    elif step == "close":
                        return
                    else:
                        conn.sendall(step)
                time.sleep(1.0)

    @property
    def url(self) -> str:
        return f"ws://127.0.0.1:{self.port}/devtools/page/x"


def reply(ident: int, result: Any) -> bytes:
    return json.dumps({"id": ident, "result": result}).encode()


def test_transport_ping_entre_fragments() -> None:
    body = reply(1, {"result": {"value": 2}})
    server = Server([frame(body[:10], fin=False), frame(b"p", opcode=0x9), frame(body[10:], opcode=0x0)])
    page = cdp_wheel._Page(server.url, timeout=1.0)
    try:
        assert page.evaluate("1 + 1") == 2
    finally:
        page.close()


@pytest.mark.parametrize(
    "script",
    [
        [frame(b"\x03\xe8", opcode=0x8)],  # Close avant la réponse
        [frame(reply(1, {}))[:5], "close"],  # trame tronquée puis fermeture
        [frame(b"[]")],  # JSON inattendu
        [frame(b"pas du json")],
        [frame(reply(1, []))],  # résultat d'un autre type
        [frame(json.dumps({"id": 7, "result": {}}).encode())],  # réponse d'une autre requête
    ],
)
def test_transport_defaillances(script: list[Any]) -> None:
    server = Server(script)
    page = cdp_wheel._Page(server.url, timeout=1.0)
    try:
        with pytest.raises(Exception):  # noqa: B017 - toute défaillance est une erreur, jamais un résultat
            page.call("Input.dispatchMouseEvent")
    finally:
        page.close()


def test_transport_accept_faux_refuse() -> None:
    server = Server([], good_accept=False)
    with pytest.raises(Exception):  # noqa: B017
        cdp_wheel._Page(server.url, timeout=1.0)


def test_transport_redirection_refusee() -> None:
    """Relecture de Codex (19:18) : websocket-client suivait un 302 vers un autre port, hors des preuves."""
    target = Server([frame(reply(1, {"result": {"value": 2}}))])
    server = Server([], redirect_to=target.port)
    with pytest.raises(Exception):  # noqa: B017
        cdp_wheel._Page(server.url, timeout=1.0)


def test_transport_fermeture_bornee() -> None:
    """Relecture de Codex (19:18) : close(timeout=0.2) attendait la poignée de fermeture (0,6 s et plus)."""
    server = Server([3.0])  # ne répond jamais, ni au Close
    page = cdp_wheel._Page(server.url, timeout=1.0)
    start = time.monotonic()
    page.close()
    assert time.monotonic() - start < 0.1


def test_transport_compte_gouttes_coupe_a_l_echeance() -> None:
    body = frame(reply(1, {}))
    server = Server([step for byte in body for step in (bytes([byte]), 0.3)])
    page = cdp_wheel._Page(server.url, timeout=1.0)
    start = time.monotonic()
    try:
        with pytest.raises(Exception):  # noqa: B017
            page.call("Input.dispatchMouseEvent")
    finally:
        page.close()
    assert time.monotonic() - start < 2.0  # échéance absolue, pas 0,3 s par octet


class Session:
    """_Page factice pour wheel() : preuves réussies, envoi qui échoue après la requête."""

    def __init__(self, url: str) -> None:
        self.window = "Doc"

    def evaluate(self, expression: str) -> Any:
        if expression == "window.devicePixelRatio":
            return 1.0
        if expression.startswith("[window.innerWidth"):
            return [800, 600]
        return None

    def call(self, method: str, **params: Any) -> dict[str, Any]:
        raise cdp_wheel.ProtocolError("réponse []")

    def close(self) -> None:
        pass


def test_toute_defaillance_apres_l_envoi_est_incertaine(monkeypatch: pytest.MonkeyPatch) -> None:
    order: list[str] = []
    monkeypatch.setattr(cdp_wheel, "_window_pid", lambda hwnd: 10)
    monkeypatch.setattr(cdp_wheel, "_command_line", lambda pid: "app --remote-debugging-port=9333")
    monkeypatch.setattr(cdp_wheel, "_listeners", lambda port: [("127.0.0.1", 10)])
    monkeypatch.setattr(cdp_wheel, "_render_surfaces", lambda hwnd: [(0, 0, 800, 600)])
    monkeypatch.setattr(cdp_wheel, "_window_title", lambda hwnd: "Doc")
    monkeypatch.setattr(cdp_wheel, "prove", lambda *a, **k: order.append("preuve"))
    monkeypatch.setattr(cdp_wheel, "_Page", Session)

    class Response:
        def __enter__(self) -> Any:
            return self

        def __exit__(self, *a: Any) -> None:
            pass

        def read(self) -> bytes:
            return json.dumps([page("Doc")]).encode()

    monkeypatch.setattr(cdp_wheel, "fetch_json_list", lambda port: Response().read())
    with pytest.raises(cdp_wheel.Uncertain):
        cdp_wheel.wheel(
            1, 10, 10, -1, 0, check=lambda: order.append("arrêt"), before_send=lambda: order.append("empreinte")
        )
    # empreinte APRÈS la preuve ; arrêt d'urgence relu APRÈS l'empreinte, juste avant l'envoi (relecture 19:18)
    assert order == ["preuve", "empreinte", "arrêt"]

    def stop() -> None:
        raise RuntimeError("arrêt d'urgence")

    calls: list[str] = []
    monkeypatch.setattr(Session, "call", lambda self, method, **p: calls.append(method) or {})
    with pytest.raises(RuntimeError, match="arrêt"):
        cdp_wheel.wheel(1, 10, 10, -1, 0, check=stop)
    assert calls == []  # STOP pendant l'empreinte : rien n'est envoyé


def test_refus_avant_toute_entree(monkeypatch: pytest.MonkeyPatch) -> None:
    sent: list[str] = []
    monkeypatch.setattr(cdp_wheel, "_window_pid", lambda hwnd: 10)
    monkeypatch.setattr(cdp_wheel, "_command_line", lambda pid: "app --remote-debugging-port=9333")
    monkeypatch.setattr(cdp_wheel, "_listeners", lambda port: [("127.0.0.1", 11)])  # écouté par un autre PID
    monkeypatch.setattr(cdp_wheel, "_Page", lambda url: sent.append(url))
    with pytest.raises(cdp_wheel.NotApplicable):
        cdp_wheel.wheel(1, 10, 10, -1, 0)
    monkeypatch.setattr(cdp_wheel, "_command_line", lambda pid: "app")
    with pytest.raises(cdp_wheel.NotApplicable):
        cdp_wheel.wheel(1, 10, 10, -1, 0)
    assert sent == []


class HttpServer:
    """Serveur HTTP local d'une réponse brute, éventuellement au compte-gouttes."""

    def __init__(self, response: bytes, drip_s: float = 0.0, keep_open: float = 0.0) -> None:
        self.sock = socket.socket()
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(1)
        self.port = self.sock.getsockname()[1]
        self.response, self.drip_s, self.keep_open = response, drip_s, keep_open
        self.request = b""
        threading.Thread(target=self.serve, daemon=True).start()

    def serve(self) -> None:
        conn, _ = self.sock.accept()
        with conn, contextlib.suppress(OSError):
            self.request = conn.recv(4096)
            if self.drip_s:
                for byte in self.response:
                    conn.sendall(bytes([byte]))
                    time.sleep(self.drip_s)
            else:
                conn.sendall(self.response)
            time.sleep(self.keep_open)  # Chromium peut garder la connexion ouverte après un corps complet


def http(body: bytes, status: str = "200 OK", length: int | None = None, with_length: bool = True) -> bytes:
    size = len(body) if length is None else length
    head = f"HTTP/1.1 {status}\r\n" + (f"Content-Length: {size}\r\n" if with_length else "") + "\r\n"
    return head.encode() + body


def test_decouverte_http_sous_echeance_absolue() -> None:
    """Relecture de Codex (19:28) : urlopen(timeout) bornait chaque lecture, pas la réponse entière."""
    body = json.dumps([page("Doc")]).encode()
    server = HttpServer(http(body))
    assert cdp_wheel.fetch_json_list(server.port, timeout=1.0) == body
    # HTTP/1.1 (en 1.0, le serveur DevTools de Chromium ferme sans répondre : relecture de Codex 19:36, vrai port)
    assert server.request.startswith(b"GET /json/list HTTP/1.1\r\n") and b"Connection: close" in server.request
    kept = HttpServer(http(body), keep_open=2.0)
    start = time.monotonic()
    assert cdp_wheel.fetch_json_list(kept.port, timeout=1.0) == body
    assert time.monotonic() - start < 0.3  # rendu dès le corps complet, sans attendre la fin de connexion
    start = time.monotonic()
    with pytest.raises(OSError):  # TimeoutError
        cdp_wheel.fetch_json_list(HttpServer(http(body), drip_s=0.05).port, timeout=0.3)
    assert time.monotonic() - start < 0.6  # échéance absolue, pas 0,05 s par octet
    with pytest.raises(ValueError):
        cdp_wheel.fetch_json_list(HttpServer(http(b"x" * 200)).port, timeout=1.0, limit=100)  # trop grande
    with pytest.raises(ValueError):
        cdp_wheel.fetch_json_list(HttpServer(http(body, with_length=False)).port, timeout=1.0)  # sans longueur
    with pytest.raises(ValueError):
        cdp_wheel.fetch_json_list(HttpServer(http(body, status="302 Found")).port, timeout=1.0)
    with pytest.raises(ValueError):
        cdp_wheel.fetch_json_list(HttpServer(http(body, length=len(body) + 10)).port, timeout=1.0)  # tronquée


def test_edge_a_onglets_tiret_demi_cadratin() -> None:
    """Titre mesuré le 22/10 (Edge à onglets avec profil) : « page - Profil 1 – Microsoft Edge »."""
    assert cdp_wheel.title_matches("Labo Web — prêt - Profil 1 – Microsoft​ Edge", "Labo Web — prêt")
    assert not cdp_wheel.title_matches("Labo Web — prêt - Profil 1 – Bloc-notes", "Labo Web — prêt")
