"""Molette Chromium (Chrome, Edge, Electron) par le protocole DevTools, en arrière-plan.

Recette B du banc commun des NexusWindows (Codex, prouvée au banc du 21/10/2026 : NexusCodex computer-use
native/Cdp.cs), portée telle quelle : Chromium ignore une molette postée par message, mais rend une molette « de
confiance » envoyée par son port de débogage, sans activer la fenêtre ni bouger le curseur.

Avant toute entrée, cinq preuves ; une seule manque : refus, RIEN n'est envoyé (``NotApplicable``) :
1. le port figure dans la ligne de commande du processus de la fenêtre (``--remote-debugging-port=N``) ;
2. ce port est ÉCOUTÉ sur l'adresse contactée (127.0.0.1, à défaut 0.0.0.0) par le PID EXACT de la fenêtre (table TCP ;
   jamais un parent ou un enfant : une appli Electron lancée par une autre avec le même port viserait l'autre) ;
3. une seule page DevTools a un titre décodé (``/json/list`` échappe en HTML) égal à celui de la fenêtre, au suffixe de
   navigateur près, et son WebSocket reste sur 127.0.0.1 et ce port ;
4. liaison prouvée : un titre aléatoire posé sur la page (seulement si son titre n'a pas changé depuis la lecture)
   apparaît dans le titre de CETTE fenêtre en moins de 0,5 s ; le titre d'origine est remis s'il y est encore (sur une
   nouvelle connexion au besoin, sinon refus dit « titre peut-être resté ») ; la fenêtre doit ne plus le montrer ;
5. exactement UNE zone de rendu visible dans la fenêtre, le point dedans, de la taille du viewport de CETTE page
   (round(inner × DPR) à ceil(DPR) px près) ; plusieurs zones (Electron multi-vues, DevTools ancré) : hors périmètre.

Puis un seul ``Input.dispatchMouseEvent`` ``mouseWheel`` ; réponse absente après l'envoi = issue inconnue
(``Uncertain``), jamais rejouée ni suivie d'une autre technique. Point écran → CSS : zone de rendu sous le point et
``devicePixelRatio`` (illisible ou invalide : refus). Transport : websocket-client (RFC 6455), échéance absolue. Sens : seul le vertical Windows s'inverse (cran vers le haut =
delta positif chez Windows, deltaY négatif chez DevTools) ; à l'horizontale, positif = vers la droite des deux côtés.
"""

from __future__ import annotations

import contextlib
import ctypes
import html
import json
import math
import re
import secrets
import socket
import struct
import threading
import time
from collections.abc import Callable, Iterable
from ctypes import wintypes
from typing import Any

import websocket

TIMEOUT_S = 2.0
PROOF_S = 0.5
_PORT = re.compile(r"--remote-debugging-port(?:=|\s+)(\d+)", re.IGNORECASE)
_SUFFIX = re.compile(r"^ [-–] (?:[^\r\n]+? [-–] )?(?:Microsoft​? Edge|Google Chrome|Chromium|Brave)$")


class NotApplicable(RuntimeError):
    """Une preuve manque : rien n'a été envoyé."""


class Uncertain(RuntimeError):
    """Molette partie sans accusé : issue inconnue, jamais rejouée."""


# --- preuves pures (testées hors ligne)
def port_from(command_line: str | None) -> int | None:
    """Port de débogage de la ligne de commande ; 0 (« choisi par Chromium ») ou absent : pas de port connu."""
    match = _PORT.search(command_line or "")
    if not match:
        return None
    port = int(match.group(1))
    return port if 0 < port < 65536 else None


def owns_port(window_pid: int, listeners: Iterable[tuple[str, int]]) -> bool:
    """Adresse contactée (127.0.0.1, à défaut 0.0.0.0) écoutée par le PID exact de la fenêtre, et par lui seul."""
    rows = list(listeners)
    for address in ("127.0.0.1", "0.0.0.0"):
        owners = {pid for addr, pid in rows if addr == address}
        if owners:
            return owners == {window_pid}
    return False


def title_matches(window_title: str, page_title: str) -> bool:
    return bool(page_title) and (
        window_title == page_title
        or (window_title.startswith(page_title) and bool(_SUFFIX.match(window_title[len(page_title) :])))
    )


def pick_page(targets: list[dict[str, Any]], window_title: str, port: int) -> str:
    """WebSocket de l'unique page dont le titre décodé correspond à la fenêtre ; sinon refus."""
    pages = [t for t in targets if t.get("type") == "page" and t.get("webSocketDebuggerUrl")]
    matching = [t for t in pages if title_matches(window_title, html.unescape(str(t.get("title") or "")))]
    if len(matching) != 1:
        raise NotApplicable(
            f"aucune page DevTools unique prouvée pour cette fenêtre ({len(pages)} pages, {len(matching)} au bon titre) : "
            "rien n'a été envoyé"
        )
    url = str(matching[0]["webSocketDebuggerUrl"])
    found = re.match(r"^ws://(127\.0\.0\.1|localhost):(\d+)(/.*)$", url)
    if not found or int(found.group(2)) != port:
        raise NotApplicable(f"WebSocket de la page hors de 127.0.0.1:{port} : rien n'a été envoyé")
    return f"ws://127.0.0.1:{port}{found.group(3)}"


def devtools_deltas(delta_y: int, delta_x: int) -> tuple[int, int]:
    """(deltaX, deltaY) DevTools d'un geste en crans Windows (delta_y > 0 = vers le haut, delta_x > 0 = droite)."""
    return delta_x * 120, -delta_y * 120


def prove(
    window_title: Callable[[], str],
    evaluate: Callable[[str], Any],
    reconnect: Callable[[], Callable[[str], Any]] | None = None,
    sleep=time.sleep,
    clock=time.monotonic,
) -> None:
    """Preuve active de la liaison fenêtre ↔ page (titre aléatoire). Le titre d'origine est lu, puis remplacé par le
    nonce SEULEMENT s'il n'a pas changé entre-temps (sinon refus, rien n'est écrit) ; remis seulement si le nonce y est
    encore, au besoin sur une nouvelle connexion (``reconnect``) ; puis on attend que le titre de la FENÊTRE ne le montre
    plus (sinon refus) : aucun artefact du nonce ne doit précéder la molette ni passer pour son effet (relecture de
    Codex, 21/10). Titre peut-être resté : ``NotApplicable`` avec ``title_left`` vrai."""
    original = evaluate("document.title")
    if not isinstance(original, str):
        raise NotApplicable("titre de la page illisible : rien n'a été envoyé")
    nonce = "nexus-" + secrets.token_hex(16)
    restore = (
        f"(() => {{ if (document.title === {json.dumps(nonce)}) document.title = {json.dumps(original)}; "
        f"return document.title !== {json.dumps(nonce)}; }})()"
    )
    seen = False
    wrapping = ""
    failure: BaseException | None = None
    try:
        try:
            posed = evaluate(
                f"(() => {{ if (document.title !== {json.dumps(original)}) return false; "
                f"document.title = {json.dumps(nonce)}; return true; }})()"
            )
        except Exception as error:  # noqa: BLE001 - réponse perdue : la pose a pu avoir lieu, nettoyage quand même
            failure = error
            posed = None
        if failure is None and posed is not True:
            raise NotApplicable("titre de la page changé pendant la preuve : rien n'a été écrit ni envoyé")
        deadline = clock() + PROOF_S
        while failure is None and not seen and clock() < deadline:
            shown = window_title()
            seen = title_matches(shown, nonce)
            if seen:
                # habillage EXACT du navigateur autour du titre de la page (relecture de Codex 19:36) : rejoué tel quel
                # au contrôle final, jamais réinterprété par l'expression (un « profil » facultatif y passait)
                wrapping = shown[len(nonce) :]
            else:
                sleep(0.02)
    finally:
        cleaned = False
        reader: Callable[[str], Any] = evaluate  # la connexion qui a nettoyé : elle relit le titre final
        connections: list[Callable[[], Callable[[str], Any]]] = [lambda: evaluate]
        if reconnect is not None:
            connections.append(reconnect)  # nouvelle connexion au même target
        for connect in connections:
            try:
                reader = connect()
                cleaned = reader(restore) is True
            except Exception:  # noqa: BLE001 - connexion cassée : nouvelle tentative, puis aveu
                cleaned = False
            if cleaned:
                break
        # Sur TOUS les chemins (pose qui lève comprise : relecture de Codex 19:18) : la FENÊTRE doit ne plus montrer
        # le nonce ; sinon, ou si la page n'a pas pu être nettoyée, refus explicite « titre peut-être resté ».
        back = False
        deadline = clock() + PROOF_S
        while cleaned and not back and clock() < deadline:
            back = not title_matches(window_title(), nonce)
            if not back:
                sleep(0.02)
        if not (cleaned and back):
            left = NotApplicable(
                "titre aléatoire peut-être resté (page non nettoyée ou fenêtre pas revenue) : rien n'a été envoyé"
            )
            left.title_left = True  # type: ignore[attr-defined]
            raise left from failure
    if failure is not None:
        raise NotApplicable(
            f"page DevTools muette pendant la preuve ({type(failure).__name__}) : rien n'a été envoyé"
        ) from failure
    if not seen:
        raise NotApplicable(
            "cette page n'est pas prouvée être la fenêtre (son titre n'y est jamais apparu) : rien n'a été envoyé"
        )
    # L'absence du nonce ne prouve pas le retour à LA page (relecture de Codex 19:28) : le titre final RÉEL de la page
    # (celui d'origine, ou celui qu'elle s'est donné entre-temps, jamais écrasé) doit être celui de la fenêtre.
    try:
        final = reader("document.title")
    except Exception as error:  # noqa: BLE001 - page muette après la preuve : rien n'est encore parti
        raise NotApplicable("titre final de la page illisible : rien n'a été envoyé") from error
    if not isinstance(final, str):
        raise NotApplicable("titre final de la page illisible : rien n'a été envoyé")
    deadline = clock() + PROOF_S
    while window_title() != final + wrapping:
        if clock() >= deadline:
            raise NotApplicable("la fenêtre ne montre pas le titre final de la page prouvée : rien n'a été envoyé")
        sleep(0.02)


MAX_LIST_BYTES = 4 * 1024 * 1024


def fetch_json_list(port: int, timeout: float = TIMEOUT_S, limit: int = MAX_LIST_BYTES) -> bytes:
    """Corps de ``GET /json/list`` sous UNE échéance absolue (connexion, envoi, lecture) et taille bornée.
    HTTP/1.1 (``Host``, ``Connection: close``) : en HTTP/1.0, le serveur DevTools de Chromium ferme sans répondre
    (relecture de Codex 19:36, vrai port). En-têtes lus jusqu'à leur fin, puis EXACTEMENT le corps annoncé par
    Content-Length (obligatoire) : rendu dès qu'il est complet, sans attendre une fin de connexion que Chromium peut
    retarder. Statut 200 exigé. Échec : OSError (dont TimeoutError) ou ValueError."""
    start = time.monotonic()

    def remaining() -> float:
        left = timeout - (time.monotonic() - start)
        if left <= 0:
            raise TimeoutError("pages DevTools : échéance dépassée")
        return left

    with socket.create_connection(("127.0.0.1", port), timeout=remaining()) as sock:

        def receive() -> bytes:
            sock.settimeout(remaining())
            chunk = sock.recv(65536)
            if not chunk:
                raise ValueError("pages DevTools : connexion fermée avant la fin de la réponse")
            return chunk

        sock.settimeout(remaining())
        sock.sendall(f"GET /json/list HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\nConnection: close\r\n\r\n".encode())
        data = b""
        while b"\r\n\r\n" not in data:
            data += receive()
            if len(data) > 65536 and b"\r\n\r\n" not in data:
                raise ValueError("pages DevTools : en-têtes trop longs")
        head, _, body = data.partition(b"\r\n\r\n")
        lines = head.split(b"\r\n")
        if not re.match(rb"^HTTP/1\.[01] 200 ", lines[0] + b" "):
            raise ValueError("pages DevTools : réponse HTTP inattendue")
        if any(line.lower().startswith(b"transfer-encoding:") for line in lines[1:]):
            raise ValueError("pages DevTools : corps découpé non pris en charge")
        values = [line.split(b":", 1)[1].strip() for line in lines[1:] if line.lower().startswith(b"content-length:")]
        if len(values) != 1 or not values[0].isdigit():
            raise ValueError("pages DevTools : longueur du corps absente ou invalide")
        length = int(values[0])
        if length > limit:
            raise ValueError("pages DevTools : réponse trop grande")
        while len(body) < length:
            body += receive()
        if len(body) != length:
            raise ValueError("pages DevTools : corps plus long qu'annoncé")
        return body


def pick_surface(
    surfaces: list[tuple[int, int, int, int]], point: tuple[int, int], css_size: tuple[float, float], ratio: float
) -> dict[str, Any]:
    """Surface de rendu de LA page prouvée, règle COMMUNE aux trois outils (relecture de Codex du 21/10, 19:18) :
    exactement UNE zone Chrome_RenderWidgetHostHWND VISIBLE dans toute la fenêtre (``surfaces`` : gauche, haut,
    largeur, hauteur), le point dedans, et sa taille physique égale à round(innerWidth × DPR) × round(innerHeight × DPR)
    à ceil(DPR) px près. Plusieurs zones visibles (Electron WebContentsView, DevTools ancré, multi-vues) : refus, hors
    périmètre. Rend le relevé (viewport CSS, DPR, rectangle, écart) pour le compte rendu."""
    if len(surfaces) != 1:
        raise NotApplicable(
            f"{len(surfaces)} zones de rendu visibles dans la fenêtre (une seule admise) : rien n'a été envoyé"
        )
    left, top, width, height = surfaces[0]
    x, y = point
    if not (left <= x < left + width and top <= y < top + height):
        raise NotApplicable("le point n'est pas dans la zone de rendu de la page : rien n'a été envoyé")
    expected = (round(css_size[0] * ratio), round(css_size[1] * ratio))
    gap = (width - expected[0], height - expected[1])
    tolerance = math.ceil(ratio)
    if abs(gap[0]) > tolerance or abs(gap[1]) > tolerance:
        raise NotApplicable(
            f"zone de rendu {width}×{height} px ≠ viewport de la page {expected[0]}×{expected[1]} px : rien n'a été envoyé"
        )
    return {"left": left, "top": top, "rect": [left, top, width, height], "css": list(css_size), "dpr": ratio,
            "gap_px": list(gap)}  # fmt: skip


# --- système (Windows)
def _command_line(pid: int) -> str | None:
    kernel32, ntdll = ctypes.WinDLL("kernel32"), ctypes.WinDLL("ntdll")
    kernel32.OpenProcess.restype = wintypes.HANDLE
    handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return None
    try:
        size = ctypes.c_ulong(0)
        ntdll.NtQueryInformationProcess(handle, 60, None, 0, ctypes.byref(size))  # ProcessCommandLineInformation
        if not size.value:
            return None
        buffer = ctypes.create_string_buffer(size.value)
        if ntdll.NtQueryInformationProcess(handle, 60, buffer, size, ctypes.byref(size)) < 0:
            return None
        length = struct.unpack_from("<H", buffer.raw, 0)[0]
        offset = 16 if ctypes.sizeof(ctypes.c_void_p) == 8 else 8
        return buffer.raw[offset : offset + length].decode("utf-16-le", errors="replace")
    finally:
        kernel32.CloseHandle(handle)


def _listeners(port: int) -> list[tuple[str, int]]:
    """(adresse IPv4, PID) des sockets à l'écoute sur ce port (TCP_TABLE_OWNER_PID_LISTENER)."""
    iphlpapi = ctypes.WinDLL("iphlpapi")
    size = wintypes.DWORD(0)
    iphlpapi.GetExtendedTcpTable(None, ctypes.byref(size), False, 2, 3, 0)
    buffer = ctypes.create_string_buffer(size.value)
    if iphlpapi.GetExtendedTcpTable(buffer, ctypes.byref(size), False, 2, 3, 0) != 0:
        return []
    count = struct.unpack_from("<I", buffer.raw, 0)[0]
    rows = []
    for i in range(count):
        _state, addr, raw_port, _raddr, _rport, pid = struct.unpack_from("<IIIIII", buffer.raw, 4 + i * 24)
        if ((raw_port & 0xFF) << 8 | (raw_port >> 8) & 0xFF) == port:
            rows.append((socket.inet_ntoa(struct.pack("<I", addr)), pid))
    return rows


def _window_pid(hwnd: int) -> int:
    pid = wintypes.DWORD()
    ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value


def _window_title(hwnd: int) -> str:
    buffer = ctypes.create_unicode_buffer(1024)
    ctypes.windll.user32.GetWindowTextW(hwnd, buffer, 1024)
    return buffer.value


def _render_surfaces(hwnd: int) -> list[tuple[int, int, int, int]]:
    """(gauche, haut, largeur, hauteur) à l'écran de TOUTES les zones de rendu Chromium visibles de la fenêtre."""
    user32 = ctypes.windll.user32
    found: list[tuple[int, int, int, int]] = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def visit(child: int, _: int) -> bool:
        name = ctypes.create_unicode_buffer(64)
        user32.GetClassNameW(child, name, 64)
        if name.value == "Chrome_RenderWidgetHostHWND" and user32.IsWindowVisible(child):
            r = wintypes.RECT()
            user32.GetWindowRect(child, ctypes.byref(r))
            if r.right > r.left and r.bottom > r.top:
                found.append((r.left, r.top, r.right - r.left, r.bottom - r.top))
        return True

    user32.EnumChildWindows(hwnd, visit, 0)
    return found


class ProtocolError(ConnectionError):
    """Réponse CDP invalide ou inattendue."""


class _Page:
    """Session DevTools d'une page sur websocket-client (RFC 6455 : ping/pong, close, fragments, Sec-WebSocket-Accept
    vérifié). Échéance ABSOLUE par opération : un serveur qui répond au compte-gouttes est coupé à l'échéance (minuterie
    qui ferme la socket), jamais attendu octet par octet."""

    def __init__(self, url: str, timeout: float = TIMEOUT_S) -> None:
        found = re.match(r"^ws://127\.0\.0\.1:(\d+)/", url)
        if not found:
            raise NotApplicable("WebSocket hors de 127.0.0.1 : rien n'a été envoyé")
        self.timeout = timeout
        raw = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        raw.settimeout(timeout)
        try:
            # connexion TCP ET poignée de main sous la MÊME échéance ; aucune redirection suivie (websocket-client en
            # suit 3 par défaut, vers n'importe quel port : relecture de Codex 19:18) ; statut 101 exigé
            with self._deadline(raw):
                raw.connect(("127.0.0.1", int(found.group(1))))
                self.ws = websocket.create_connection(
                    url, socket=raw, timeout=timeout, suppress_origin=True, redirect_limit=0
                )
            if self.ws.getstatus() != 101:
                raise ProtocolError(f"poignée de main WebSocket refusée (statut {self.ws.getstatus()})")
        except BaseException:
            raw.close()
            raise
        self.next_id = 0

    @contextlib.contextmanager
    def _deadline(self, sock: socket.socket):
        def cut() -> None:
            with contextlib.suppress(OSError):
                sock.shutdown(socket.SHUT_RDWR)

        timer = threading.Timer(self.timeout, cut)
        timer.daemon = True
        timer.start()
        try:
            yield
        finally:
            timer.cancel()

    def call(self, method: str, **params: Any) -> dict[str, Any]:
        self.next_id += 1
        ident = self.next_id
        start = time.monotonic()
        sock = self.ws.sock
        if sock is None:
            raise ConnectionError(f"{method} : WebSocket fermé")
        with self._deadline(sock):
            self.ws.send(json.dumps({"id": ident, "method": method, "params": params}))
            while True:
                remaining = self.timeout - (time.monotonic() - start)
                if remaining <= 0:
                    raise TimeoutError(f"{method} : pas de réponse")
                self.ws.settimeout(remaining)
                raw = self.ws.recv()
                try:
                    reply = json.loads(raw)
                except ValueError as error:
                    raise ProtocolError(f"{method} : réponse illisible") from error
                if not isinstance(reply, dict):
                    raise ProtocolError(f"{method} : réponse inattendue ({type(reply).__name__})")
                if "id" not in reply:
                    continue  # évènement de la page
                if reply["id"] != ident:
                    raise ProtocolError(f"{method} : réponse d'une autre requête")
                if "error" in reply:
                    raise ProtocolError(f"{method} : {reply['error']}")
                result = reply.get("result")
                if not isinstance(result, dict):
                    raise ProtocolError(f"{method} : résultat absent ou inattendu")
                return result

    def evaluate(self, expression: str) -> Any:
        result = self.call("Runtime.evaluate", expression=expression, returnByValue=True)
        if "exceptionDetails" in result or not isinstance(result.get("result"), dict):
            raise ProtocolError("Runtime.evaluate : exception ou résultat inattendu")
        return result["result"].get("value")

    def close(self) -> None:
        """Abandon immédiat de la connexion (shutdown de la socket), sans attendre la poignée de fermeture : borné, même
        face à une page qui ne répond plus (relecture de Codex 19:18 : close(timeout=0.2) prenait 0,6 s et plus)."""
        with contextlib.suppress(Exception):
            self.ws.shutdown()


_BEFORE_SEND = (OSError, ConnectionError, TimeoutError, ValueError, websocket.WebSocketException)


def wheel(
    hwnd: int,
    x: int,
    y: int,
    delta_y: int,
    delta_x: int,
    check: Callable[[], None] = lambda: None,
    before_send: Callable[[], None] = lambda: None,
) -> dict[str, Any]:
    """Molette au point écran (x, y) de la fenêtre Chromium `hwnd`, en crans Windows. NotApplicable : rien n'est parti ;
    Uncertain : envoyée sans accusé valide ; sinon {"technique", "mechanism", "port"} (envoyée, accusée).
    ``before_send`` : appelé après toutes les preuves (titre de la fenêtre revenu), juste avant l'envoi (empreinte de
    l'appelant prise APRÈS le nonce)."""
    pid = _window_pid(hwnd)
    port = port_from(_command_line(pid))
    if port is None:
        raise NotApplicable(
            "Chromium ignore la molette postée et la fenêtre n'a pas de port de débogage : rien n'a été envoyé"
        )
    if not owns_port(pid, _listeners(port)):
        raise NotApplicable(f"port de débogage {port} non écouté par le processus de la fenêtre : rien n'a été envoyé")
    surfaces = _render_surfaces(hwnd)
    try:
        targets = json.loads(fetch_json_list(port).decode("utf-8"))
        if not isinstance(targets, list):
            raise ValueError("liste des pages inattendue")
    except (OSError, ValueError) as error:
        raise NotApplicable(f"pages DevTools illisibles ({type(error).__name__}) : rien n'a été envoyé") from error
    url = pick_page(targets, _window_title(hwnd), port)
    try:
        page = _Page(url)
    except _BEFORE_SEND as error:
        raise NotApplicable(f"page DevTools injoignable ({type(error).__name__}) : rien n'a été envoyé") from error
    spare: list[_Page] = []

    def reconnect() -> Callable[[str], Any]:
        fresh = _Page(url)
        spare.append(fresh)
        return fresh.evaluate

    try:
        try:
            prove(lambda: _window_title(hwnd), page.evaluate, reconnect)
            ratio = page.evaluate("window.devicePixelRatio")
            size = page.evaluate("[window.innerWidth, window.innerHeight]")
        except _BEFORE_SEND as error:
            raise NotApplicable(
                f"page DevTools muette avant l'envoi ({type(error).__name__}) : rien n'a été envoyé"
            ) from error
        if isinstance(ratio, bool) or not isinstance(ratio, (int, float)) or not 0.1 < ratio < 16:
            raise NotApplicable("devicePixelRatio illisible : rien n'a été envoyé")
        if not (isinstance(size, list) and len(size) == 2 and all(isinstance(v, (int, float)) and v > 0 for v in size)):
            raise NotApplicable("taille du viewport de la page illisible : rien n'a été envoyé")
        surface = pick_surface(surfaces, (x, y), (float(size[0]), float(size[1])), float(ratio))
        left, top = surface["left"], surface["top"]
        dx, dy = devtools_deltas(delta_y, delta_x)
        before_send()  # empreinte de l'appelant (peut prendre du temps)
        check()  # arrêt d'urgence relu APRÈS l'empreinte, juste avant l'entrée (relecture de Codex 19:18)
        try:
            page.call("Input.dispatchMouseEvent", type="mouseWheel", x=(x - left) / ratio, y=(y - top) / ratio,
                      deltaX=dx, deltaY=dy)  # fmt: skip
        except Exception as error:  # noqa: BLE001 - toute défaillance APRÈS l'envoi : issue inconnue, jamais rejouée
            raise Uncertain("molette DevTools envoyée sans accusé valide : issue inconnue, ne pas rejouer") from error
        return {
            "technique": "molette DevTools",
            "mechanism": f"Input.dispatchMouseEvent mouseWheel (port {port})",
            "port": port,
            "surface": {k: v for k, v in surface.items() if k not in ("left", "top")},
        }
    finally:
        page.close()
        for fresh in spare:
            fresh.close()
