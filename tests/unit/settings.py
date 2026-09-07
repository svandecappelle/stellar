# -*- coding: utf-8 -*-

"""
Les reglages de partie : ce qu'ils acceptent, et ce qu'ils rendent.

Un reglage n'est pas une regle du jeu, c'est un bouton pose dessus. D'ou les
deux exigences que ces tests tiennent, et qui tirent en sens contraire :

  · a l'ecriture, on refuse tout ce qui n'est pas clair. Un moderateur qui tape
    une valeur hors bornes s'est trompe de champ ; la lui ramener en silence lui
    ferait croire qu'elle est passee ;
  · a la lecture, on ne casse jamais rien. Une galaxie inconnue, une ligne
    absente, une valeur illisible en base : le defaut reprend la main. Une
    partie ne doit pas s'arreter parce qu'un bouton a mal tourne.

Les valeurs par defaut valent toutes 1.0 et ne changent donc rien : c'est ce qui
permet a une galaxie sans ligne de reglages de se jouer exactement comme avant
que ces reglages n'existent. Ce dernier point est verifie ici plutot que suppose
-- il est la promesse faite aux parties deja en cours.
"""

import pytest

from app.models.game.settings import (
    DEFAULTS, PARAMETERS, PARAMETERS_BY_KEY, GalaxySettings)


@pytest.fixture(name="overrides", autouse=True)
def overrides(monkeypatch):
    """
    Une base ou rien n'est pose, et de quoi y poser des reglages.
    ---
    `row_for` est la seule methode qui touche la base ; on la remplace par un
    dictionnaire. Tout le reste -- resolution des defauts, filtrage des cles
    inconnues, conversion -- est du calcul, et c'est lui qu'on vient eprouver.

    Toujours active : sans elle, une galaxie nommee irait interroger une base
    qui n'existe pas ici, alors que ce qu'on veut lui faire dire est justement
    ce qu'elle repond quand elle ne trouve rien.
    """
    rows = {}
    monkeypatch.setattr(
        GalaxySettings, 'row_for',
        classmethod(lambda cls, galaxy_name: rows.get(galaxy_name)))

    def written(values, galaxy_name="test"):
        rows[galaxy_name] = GalaxySettings(
            galaxy_name=galaxy_name, overrides=values)
        return rows[galaxy_name]
    return written


class TestParameterCleaning:

    @pytest.mark.parametrize("raw,expected", [(2, 2.0), ("0.5", 0.5), (1.25, 1.25)])
    def test_a_number_comes_back_as_a_float(self, raw, expected):
        """
        Un entier, une chaine, un flottant : tous rendent un flottant.
        ---
        Les reglages arrivent d'un formulaire HTML, donc en texte, et d'appels
        d'API, donc en JSON type. Ils sont ensuite multiplies a des durees et a
        des productions : un seul type en sortie, et la multiplication ne
        surprend personne.
        """
        assert PARAMETERS_BY_KEY['build_time_divider'].clean(raw) == expected

    @pytest.mark.parametrize("raw", [None, "vite", "", [], {}])
    def test_what_is_not_a_number_is_refused(self, raw):
        parameter = PARAMETERS_BY_KEY['build_time_divider']
        with pytest.raises(ValueError, match="n'est pas un nombre"):
            parameter.clean(raw)

    @pytest.mark.parametrize("raw", [float('nan'), float('inf'), float('-inf')])
    def test_what_is_not_a_real_number_is_refused(self, raw):
        """
        L'infini et le non-nombre passent les bornes sans les franchir.
        ---
        `nan` est faux dans toute comparaison : il traverserait le test des
        bornes intact, puis multiplierait chaque production de la galaxie pour
        la rendre elle-meme non-numerique. Il faut donc l'ecarter avant.
        """
        with pytest.raises(ValueError, match="hors du domaine reel"):
            PARAMETERS_BY_KEY['build_time_divider'].clean(raw)

    def test_a_value_out_of_bounds_is_refused_not_clamped(self):
        """
        Hors bornes, on refuse : on ne ramene pas.
        ---
        Le moderateur qui tape 10000 s'est trompe de champ. Lui rendre 1000 sans
        rien dire lui laisserait croire que sa valeur est passee, et il
        chercherait ailleurs pourquoi la partie ne s'accelere pas.
        """
        parameter = PARAMETERS_BY_KEY['build_time_divider']

        with pytest.raises(ValueError, match="hors des bornes"):
            parameter.clean(parameter.maximum + 1)
        with pytest.raises(ValueError, match="hors des bornes"):
            parameter.clean(parameter.minimum / 2)

    def test_the_bounds_themselves_are_allowed(self):
        parameter = PARAMETERS_BY_KEY['build_time_divider']

        assert parameter.clean(parameter.minimum) == parameter.minimum
        assert parameter.clean(parameter.maximum) == parameter.maximum

    def test_every_default_sits_within_its_own_bounds(self):
        """
        Un defaut hors bornes serait un reglage impossible a remettre a zero.
        """
        for parameter in PARAMETERS:
            assert parameter.clean(parameter.default) == parameter.default

    def test_a_parameter_describes_itself_to_the_console(self):
        """
        Le libelle et les bornes voyagent avec le reglage.
        ---
        C'est le serveur qui applique le reglage : c'est a lui de dire ce qu'il
        fait. La console batit son formulaire a partir de cette description, et
        n'a donc aucune copie des bornes a tenir a jour.
        """
        serialized = PARAMETERS_BY_KEY['extraction_multiplier'].serialize

        assert serialized['key'] == 'extraction_multiplier'
        assert serialized['label']
        assert serialized['description']
        assert serialized['min'] < serialized['default'] < serialized['max']
        assert serialized['step'] > 0


class TestEffectiveValues:

    def test_a_galaxy_without_a_row_plays_by_the_defaults(self):
        """
        Rien de pose, rien de change : c'est la promesse faite aux parties
        deja en cours, et elle tient a ce que tous les defauts valent 1.0.
        """
        assert set(DEFAULTS) == set(PARAMETERS_BY_KEY)
        assert set(DEFAULTS.values()) == {1.0}
        assert GalaxySettings.effective_for("inconnue") == DEFAULTS

    def test_a_written_value_takes_over_its_default(self, overrides):
        overrides({'build_time_divider': 4.0})
        values = GalaxySettings.effective_for("test")

        assert values['build_time_divider'] == 4.0
        # Les autres n'ont pas bouge.
        assert values['extraction_multiplier'] == DEFAULTS['extraction_multiplier']

    def test_a_key_nobody_recognises_is_ignored(self, overrides):
        """
        Une cle inconnue en base ne remonte pas jusqu'au jeu.
        ---
        La colonne est un JSON libre : un reglage retire du code laisse sa
        valeur derriere lui dans les lignes deja ecrites. Le lire ferait entrer
        dans le jeu un parametre que plus personne n'applique.
        """
        overrides({'build_time_divider': 4.0, 'vitesse_lumiere': 12})
        values = GalaxySettings.effective_for("test")

        assert 'vitesse_lumiere' not in values
        assert set(values) == set(DEFAULTS)


class TestValueLookup:

    def test_a_value_is_read_as_a_float(self, overrides):
        """
        Ce que rend `value` multiplie des durees et des productions.
        ---
        La colonne est un JSON : elle peut rendre une chaine selon qui l'a
        ecrite. Multiplier une duree par "2" repeterait la chaine au lieu de
        doubler le nombre.
        """
        overrides({'fleet_speed_multiplier': "2"})
        assert GalaxySettings.value("test", 'fleet_speed_multiplier') == 2.0

    def test_an_unreadable_value_falls_back_on_the_default(self, overrides):
        overrides({'fleet_speed_multiplier': "tres vite"})
        assert GalaxySettings.value("test", 'fleet_speed_multiplier') == 1.0

    def test_an_unknown_galaxy_gets_the_default(self):
        assert GalaxySettings.value("inconnue", 'build_time_divider') == 1.0

    def test_a_galaxy_without_a_name_gets_the_default(self):
        """
        Un territoire hors systeme n'a pas de galaxie, et se joue quand meme.
        ---
        `Territory.galaxy_name` rend None des que le systeme n'est pas charge :
        c'est cette valeur-la qui arrive ici, a chaque batiment serialise.
        """
        assert GalaxySettings.value(None, 'build_time_divider') == 1.0

    def test_a_setting_that_cannot_be_read_never_breaks_the_game(self, monkeypatch):
        """
        Une lecture en echec rend le defaut, elle ne remonte pas.
        ---
        Le cas reel : la table n'existe pas encore sur une base en retard d'une
        migration. Un reglage est un confort ; il ne doit pas pouvoir empecher
        une partie de se jouer.
        """
        def broken(cls, galaxy_name):
            raise RuntimeError("relation « galaxy_settings » n'existe pas")

        monkeypatch.setattr(GalaxySettings, 'row_for', classmethod(broken))

        assert GalaxySettings.value("test", 'build_time_divider') == 1.0

    def test_an_unknown_key_is_neutral(self):
        """
        Un reglage qui n'existe pas vaut 1.0, donc ne change rien.
        ---
        Le sens de tous les reglages : un multiplicateur. Rendre 0 ferait
        disparaitre la production, rendre None ferait lever la multiplication.
        """
        assert GalaxySettings.value("test", 'reglage_imaginaire') == 1.0
