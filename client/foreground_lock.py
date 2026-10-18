#!/usr/bin/env python3
"""
Jeton commun aux agents de Julien (NexusAGY, NexusClaude, NexusCodex) : souris et premier plan.

Implémentation Python de référence du protocole `foreground-token.md` (même dossier). Tenir le jeton = verrou
exclusif LockFileEx sur l'octet 2^32 de `%USERPROFILE%\\.nexus\\foreground.lock` : local au poste (jamais dans
OneDrive), libéré par Windows à la fermeture du handle, donc à la mort du processus (aucun jeton périmé).
Le verrou appartient au handle : deux instances, même dans un seul processus, s'excluent.
"""

from __future__ import annotations

import ctypes
import json
import os
import threading
import time
from collections.abc import Callable
from ctypes import wintypes as w
from pathlib import Path

LOCK_FILE = Path.home() / ".nexus" / "foreground.lock"
DEFAULT_TIMEOUT_S = 8.0
POLL_S = 0.05

_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)


class _OVERLAPPED(ctypes.Structure):
    _fields_ = [
        ("Internal", ctypes.c_size_t),
        ("InternalHigh", ctypes.c_size_t),
        ("Offset", w.DWORD),
        ("OffsetHigh", w.DWORD),
        ("hEvent", w.HANDLE),
    ]


def _fn(name, restype, *argtypes):
    func = getattr(_kernel32, name)
    func.restype = restype
    func.argtypes = list(argtypes)
    return func


_CreateFileW = _fn("CreateFileW", w.HANDLE, w.LPCWSTR, w.DWORD, w.DWORD, w.LPVOID, w.DWORD, w.DWORD, w.HANDLE)
_LockFileEx = _fn("LockFileEx", w.BOOL, w.HANDLE, w.DWORD, w.DWORD, w.DWORD, w.DWORD, ctypes.POINTER(_OVERLAPPED))
_UnlockFileEx = _fn("UnlockFileEx", w.BOOL, w.HANDLE, w.DWORD, w.DWORD, w.DWORD, ctypes.POINTER(_OVERLAPPED))
_WriteFile = _fn("WriteFile", w.BOOL, w.HANDLE, w.LPCVOID, w.DWORD, ctypes.POINTER(w.DWORD), w.LPVOID)
_SetFilePointerEx = _fn("SetFilePointerEx", w.BOOL, w.HANDLE, ctypes.c_longlong, ctypes.c_void_p, w.DWORD)
_SetEndOfFile = _fn("SetEndOfFile", w.BOOL, w.HANDLE)
_CloseHandle = _fn("CloseHandle", w.BOOL, w.HANDLE)

_INVALID = w.HANDLE(-1).value


def _region() -> _OVERLAPPED:
    region = _OVERLAPPED()
    region.OffsetHigh = 1  # octet 2^32
    return region


def _open() -> int:
    LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    handle = _CreateFileW(str(LOCK_FILE), 0xC0000000, 0x7, None, 4, 0x80, None)  # RW, partage total, OPEN_ALWAYS
    if not handle or handle == _INVALID:
        raise OSError(ctypes.get_last_error(), f"jeton commun inaccessible : {LOCK_FILE}")
    return handle


def _write(handle: int, text: str) -> None:
    data = text.encode("utf-8")
    _SetFilePointerEx(handle, 0, None, 0)
    written = w.DWORD()
    _WriteFile(handle, data, len(data), ctypes.byref(written), None)
    _SetEndOfFile(handle)


def holder() -> dict | None:
    """Qui tient le jeton ({owner, pid, since, purpose}), ou None s'il est libre. Diagnostic : seul le verrou fait foi."""
    handle = _open()
    try:
        if _LockFileEx(handle, 0x3, 0, 1, 0, ctypes.byref(_region())):
            _UnlockFileEx(handle, 0, 1, 0, ctypes.byref(_region()))
            return None
    finally:
        _CloseHandle(handle)
    try:
        return json.loads(LOCK_FILE.read_text(encoding="utf-8") or "{}")
    except (OSError, ValueError):
        return {}


# Prises en cours dans CE processus, par agent ET par fil : {(owner, fil): profondeur}. Un fil qui imbrique ses gardes
# (un clic qui appelle une touche, chacun avec sa garde) ne s'attend pas lui-même ; un autre fil du même agent (appel
# abandonné encore en cours, nouvel appel) attend le verrou comme un autre agent : jamais deux gestes à la fois.
_NESTED: dict[tuple[str, int], int] = {}
_NESTED_LOCK = threading.Lock()


class ForegroundLock:
    """with ForegroundLock("NexusAGY", purpose="clic physique"): ... — attend au plus `timeout` secondes.

    Réentrant par agent et par fil : une instance du même `owner`, ouverte dans le même fil pendant qu'une autre tient
    déjà le jeton, l'obtient aussitôt, sans second verrou ; le jeton n'est rendu qu'à la sortie de la plus extérieure.
    `abort` (facultatif) est appelé à chaque tour d'attente : il lève une exception pour interrompre l'attente
    (arrêt d'urgence), le handle étant alors fermé."""

    def __init__(
        self,
        owner: str = "NexusAGY",
        timeout: float = DEFAULT_TIMEOUT_S,
        purpose: str = "",
        abort: Callable[[], None] | None = None,
    ):
        self.owner = owner
        self.timeout = timeout
        self.purpose = purpose
        self.abort = abort
        self.acquired = False
        self._handle: int | None = None
        self._nested = False
        self._key = (owner, threading.get_ident())

    def acquire(self) -> bool:
        """Vrai si le jeton est à nous ; faux après `timeout` (un autre agent le tient : ne pas agir)."""
        if self.acquired:
            return True
        self._key = (self.owner, threading.get_ident())
        with _NESTED_LOCK:
            if _NESTED.get(self._key, 0) > 0:
                _NESTED[self._key] += 1
                self._nested, self.acquired = True, True
                return True
        handle = _open()
        deadline = time.monotonic() + self.timeout
        try:
            while not _LockFileEx(handle, 0x3, 0, 1, 0, ctypes.byref(_region())):  # exclusif, sans attendre
                if self.abort is not None:
                    self.abort()
                if time.monotonic() >= deadline:
                    _CloseHandle(handle)
                    return False
                time.sleep(POLL_S)
        except BaseException:
            _CloseHandle(handle)
            raise
        _write(
            handle, json.dumps({"owner": self.owner, "pid": os.getpid(), "since": time.time(), "purpose": self.purpose})
        )
        self._handle, self.acquired = handle, True
        with _NESTED_LOCK:
            _NESTED[self._key] = 1
        return True

    def release(self) -> None:
        if not self.acquired:
            return
        if self._nested:
            self._nested, self.acquired = False, False
            with _NESTED_LOCK:
                if _NESTED.get(self._key, 0) > 1:  # la prise extérieure a pu être rendue avant (sortie dans le désordre)
                    _NESTED[self._key] -= 1
            return
        if self._handle is None:
            return
        with _NESTED_LOCK:
            _NESTED.pop(self._key, None)
        handle, self._handle, self.acquired = self._handle, None, False
        try:
            _write(handle, "")
            _UnlockFileEx(handle, 0, 1, 0, ctypes.byref(_region()))
        finally:
            _CloseHandle(handle)

    def __enter__(self) -> ForegroundLock:
        if not self.acquire():
            who = holder() or {}
            raise TimeoutError(
                f"{who.get('owner') or 'un autre agent'} tient la souris et le premier plan "
                f"({who.get('purpose') or 'action physique'}) : action reportée, rien n'a été fait"
            )
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.release()
