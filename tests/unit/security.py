# -*- coding: utf-8 -*-

"""
Les decisions cryptographiques de l'application.

Trois sujets qui ne se rencontrent nulle part ailleurs : la cle qui signe les
sessions, la facon dont un mot de passe est range, et la fabrication d'un jeton
d'appareil. Aucun n'a besoin d'une base — ce sont des fonctions pures, et c'est
ce qui permet de les lancer a chaque frappe.

Ce que ces tests protegent tient en une phrase : ce fichier-la est le seul du
projet dont une regression ne se voit pas. Un mot de passe mal range se verifie
quand meme, une cle previsible signe des cookies parfaitement valides, un jeton
tire sans hasard s'echange sans erreur. Rien ne casse — jusqu'a la fuite.
"""

import re

import pytest

from app.security import (
    DEFAULT_PASSWORD_METHOD, LEGACY_HASH, MAX_PASSWORD_LENGTH,
    MIN_PASSWORD_LENGTH, SECRET_KEY_ENV, WeakPassword, check_password_policy,
    hash_password, needs_rehash, new_token, secret_key, token_digest,
    verify_password)


@pytest.fixture(name="no_source")
def without_any_configured_key(monkeypatch):
    """
    Ni environnement ni configuration : le cas du repli.
    ---
    `config/test.ini` porte une cle fixe pour que le journal de la suite reste
    lisible. Les tests du repli doivent donc la retirer, sans quoi ils
    n'eprouveraient que cette cle-la.
    """
    from config.configuration import AppConfig

    monkeypatch.delenv(SECRET_KEY_ENV, raising=False)
    monkeypatch.setattr(AppConfig, 'has', classmethod(lambda cls, s, k: False))
    return monkeypatch


#: L'ancienne forme, telle que la posait `User.new` avant scrypt.
def legacy(plain):
    import hashlib
    return hashlib.sha256(plain.encode('utf-8')).hexdigest()


class TestTheSessionKey:
    """
    La cle qui signe les cookies de session.
    ---
    Elle etait une constante ecrite dans le depot. Quiconque en avait lu le code
    pouvait forger un cookie pour n'importe quel compte, administrateur compris,
    sans jamais toucher a un mot de passe.
    """

    def test_the_environment_wins(self, monkeypatch):
        monkeypatch.setenv(SECRET_KEY_ENV, "une-cle-posee-par-le-conteneur")

        assert secret_key() == "une-cle-posee-par-le-conteneur"

    def test_the_configuration_comes_next(self, monkeypatch):
        from config.configuration import AppConfig

        monkeypatch.delenv(SECRET_KEY_ENV, raising=False)
        monkeypatch.setattr(
            AppConfig, 'has',
            classmethod(lambda cls, section, key: (section, key) == ('security', 'secret_key')))
        monkeypatch.setattr(
            AppConfig, 'get',
            classmethod(lambda cls, section, key: "une-cle-du-fichier"))

        assert secret_key() == "une-cle-du-fichier"

    def test_an_empty_configured_key_falls_through(self, monkeypatch):
        """
        `secret_key =` sans valeur : une cle vide signe tout aussi bien, et
        serait prise avant le repli.
        """
        from config.configuration import AppConfig

        monkeypatch.delenv(SECRET_KEY_ENV, raising=False)
        monkeypatch.setattr(AppConfig, 'has', classmethod(lambda cls, s, k: True))
        monkeypatch.setattr(AppConfig, 'get', classmethod(lambda cls, s, k: ""))

        assert secret_key() != ""
        assert len(secret_key()) >= 32

    def test_without_a_source_each_call_draws_a_new_key(self, no_source):
        """
        Un repli CONSTANT serait le defaut qu'on vient de retirer : previsible,
        donc forgeable. Un repli aleatoire ne coute qu'une chose — les sessions
        ne survivent pas a un redemarrage — et le jeton d'appareil en rouvre une
        aussitot.
        """
        assert secret_key() != secret_key()

    def test_the_fallback_is_long_enough_to_be_out_of_reach(self, no_source):
        assert len(secret_key()) >= 32

    def test_an_empty_environment_variable_does_not_count(self, no_source):
        """
        `STELLAR_SECRET_KEY=` dans un fichier d'environnement mal rempli : la
        cle vide signerait tout aussi bien, et serait la premiere essayee.
        """
        no_source.setenv(SECRET_KEY_ENV, "")

        assert secret_key() != ""
        assert len(secret_key()) >= 32


class TestThePasswordPolicy:

    def test_a_short_password_is_refused(self):
        with pytest.raises(WeakPassword):
            check_password_policy("a" * (MIN_PASSWORD_LENGTH - 1))

    def test_a_password_of_the_minimum_length_passes(self):
        assert check_password_policy("a" * MIN_PASSWORD_LENGTH)

    def test_an_enormous_password_is_refused(self):
        """
        Sans plafond, une requete de connexion peut imposer au serveur de hacher
        un megaoctet — a cent millisecondes le hachage, quelques requetes
        suffisent a l'occuper entierement.
        """
        with pytest.raises(WeakPassword):
            check_password_policy("a" * (MAX_PASSWORD_LENGTH + 1))

    def test_nothing_at_all_is_refused(self):
        with pytest.raises(WeakPassword):
            check_password_policy(None)

        with pytest.raises(WeakPassword):
            check_password_policy("")

    def test_a_long_passphrase_passes(self):
        """
        Aucune regle de composition : imposer une majuscule et un chiffre
        produit `Password1`, la longueur est la seule contrainte qui compte.
        """
        assert check_password_policy("correct cheval batterie agrafe")


class TestRangingAPassword:

    def test_a_password_verifies_against_its_own_hash(self):
        stored = hash_password("un mot de passe")

        assert verify_password(stored, "un mot de passe")
        assert not verify_password(stored, "un autre")

    def test_the_password_is_not_in_what_is_stored(self):
        stored = hash_password("un mot de passe")

        assert "un mot de passe" not in stored

    def test_the_same_password_is_ranged_differently_twice(self):
        """
        Le sel. Sans lui, deux joueurs qui choisissent le meme mot de passe
        portent la meme empreinte — et une seule table pre-calculee les rend
        tous les deux.
        """
        assert hash_password("identique") != hash_password("identique")

    def test_the_hash_is_not_the_legacy_shape(self):
        assert not LEGACY_HASH.match(hash_password("un mot de passe"))

    def test_the_default_method_is_the_strong_one(self):
        """
        `[security] password_method` n'existe que pour la suite de tests. Si le
        defaut cessait d'etre celui de werkzeug, une installation sans cette
        ligne — c'est-a-dire la production — se retrouverait affaiblie sans que
        rien ne le dise.
        """
        assert DEFAULT_PASSWORD_METHOD is None


class TestTheAccountsThatCameBefore:
    """
    Les comptes ranges en SHA-256 nu, sans sel ni cout.
    ---
    Une empreinte ne se remonte pas : on ne peut donc pas les convertir en base.
    Le seul instant ou le serveur tient le mot de passe en clair est celui de la
    connexion, et c'est la que la conversion doit se faire. En attendant, ils
    doivent continuer a fonctionner — leur fermer la porte au nom de leur
    protection serait un drole de service.
    """

    def test_a_legacy_password_still_verifies(self):
        assert verify_password(legacy("ancien"), "ancien")
        assert not verify_password(legacy("ancien"), "faux")

    def test_a_legacy_hash_is_recognised_as_needing_a_rehash(self):
        assert needs_rehash(legacy("ancien"))

    def test_a_current_hash_does_not(self):
        assert not needs_rehash(hash_password("actuel"))

    def test_the_legacy_shape_is_recognised_by_its_form_alone(self):
        """
        Soixante-quatre caracteres hexadecimaux. Une empreinte werkzeug porte
        des `$` et le nom de sa methode : les deux formes ne peuvent pas se
        confondre.
        """
        assert LEGACY_HASH.match("0" * 64)
        assert not LEGACY_HASH.match("0" * 63)
        assert not LEGACY_HASH.match("g" * 64)
        assert not LEGACY_HASH.match("scrypt:32768:8:1$abc$def")


class TestARefusalIsNeverAnError:
    """
    Une empreinte illisible vaut un refus, jamais une erreur cinq cents : sans
    cela, un champ tronque en base ferait tomber la route de connexion.
    """

    @pytest.mark.parametrize("stored", [
        None, "", "pas une empreinte", "scrypt$incomplet",
        "methode-inconnue$sel$empreinte",
    ])
    def test_a_broken_hash_refuses(self, stored):
        assert not verify_password(stored, "quoi que ce soit")

    def test_an_empty_password_refuses(self):
        assert not verify_password(hash_password("un mot de passe"), "")
        assert not verify_password(hash_password("un mot de passe"), None)

    def test_nothing_at_all_needs_no_rehash(self):
        assert not needs_rehash(None)
        assert not needs_rehash("")


class TestDeviceTokens:

    def test_two_tokens_are_never_the_same(self):
        assert new_token() != new_token()

    def test_a_token_is_long_enough_to_be_out_of_reach(self):
        """
        Trente-deux octets tires au hasard, transportes en base64 : quarante
        caracteres au moins. C'est ce qui rend la recherche exhaustive vaine, et
        c'est aussi pourquoi l'empreinte d'un jeton n'a pas besoin de scrypt.
        """
        assert len(new_token()) >= 40

    def test_a_token_travels_in_a_url_without_being_encoded(self):
        assert re.match(r'^[A-Za-z0-9_-]+$', new_token())

    def test_the_digest_is_stable(self):
        token = new_token()

        assert token_digest(token) == token_digest(token)

    def test_two_tokens_have_two_digests(self):
        assert token_digest(new_token()) != token_digest(new_token())

    def test_the_token_is_not_in_its_digest(self):
        """
        Le serveur ne garde que l'empreinte : un vol de la base ne doit pas
        rendre les jetons utilisables, exactement comme pour les mots de passe.
        """
        token = new_token()

        assert token not in token_digest(token)

    def test_nothing_digests_to_nothing(self):
        assert token_digest(None) is None
        assert token_digest("") is None
