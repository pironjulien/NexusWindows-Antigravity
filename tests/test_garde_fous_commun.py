"""Accord Claude–Antigravity « garde-fous » du 18/10/2026 : le Computer Use lit la politique COMMUNE
(NexusHarness/NexusWindows/commun/garde-fous.json) au lieu de ses listes en dur, sans changer son comportement de 2.8.1."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "client"))

import computer_client  # noqa: E402
import garde_fous  # noqa: E402  (chargé par computer_client depuis NexusWindows/commun/)

# Comportement de 2.8.1, figé : bureau sécurisé et gestionnaires de mots de passe ; ni la fenêtre d'identifiants
# Windows ni la propre fenêtre d'Antigravity ne sont bloquées (catégories « antigravity » de garde-fous.json).
PROTECTED_2_8_1 = {"consent.exe", "lockapp.exe", "logonui.exe"}
PASSWORD_MANAGERS_2_8_1 = ("keepass", "bitwarden", "1password", "dashlane", "nordpass", "roboform", "lastpass")


def test_policy_is_the_shared_file():
    assert computer_client.SHARED_DIR.name == "commun"
    assert Path(garde_fous.__file__).resolve().parent == computer_client.SHARED_DIR
    assert garde_fous.POLICY_FILE.name == "garde-fous.json"


def test_lists_come_from_the_shared_policy():
    assert computer_client.CONFIRM_PATTERNS == garde_fous.confirm_patterns()
    assert computer_client.CONTEXT_CONFIRM == garde_fous.confirm_contexts()
    assert computer_client.NON_ACTION_ROLES == garde_fous.non_action_roles()
    assert computer_client.TRIGGER_ROLES == garde_fous.trigger_roles()
    assert computer_client.PASSWORD_MANAGER_PREFIXES == garde_fous.password_manager_prefixes()


def test_hard_block_unchanged_since_2_8_1():
    assert computer_client.PROTECTED_PROCESS_NAMES == PROTECTED_2_8_1
    assert computer_client.PROTECTED_WINDOW_CLASSES == set()
    assert computer_client.PASSWORD_MANAGER_PREFIXES == PASSWORD_MANAGERS_2_8_1
    assert garde_fous.hard_block_reason("antigravity", "credentialuibroker.exe") == ""
    assert garde_fous.hard_block_reason("antigravity", "claude.exe") == ""  # l'AUTRE agent : permis
    assert garde_fous.hard_block_reason("antigravity", "KeePassXC.exe")


def test_confirmation_words_unchanged():
    for label in ("Envoyer", "Payer", "Publier", "Supprimer définitivement", "Désinstaller", "Formater",
                  "Réinitialiser ce PC", "Résilier", "Rendre le dépôt public"):  # fmt: skip
        assert computer_client.irreversible_word(label), label
    for label in ("Éléments envoyés", "Supprimer", "Réinitialiser les filtres", "Déployer", "Formater le document"):
        assert not computer_client.irreversible_word(label), label
