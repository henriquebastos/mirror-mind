"""Testes para memoria.extraction — foco em normalização de slugs."""

import pytest

from memoria.extraction import normalize_travessia_slug, resolve_travessia


class TestNormalizeTravessiaSlug:
    @pytest.mark.parametrize(
        "raw, expected",
        [
            # Casos básicos
            ("mirror-mind", "mirror-mind"),
            ("ia-fronteira", "ia-fronteira"),
            # Acentos
            ("organização-digital", "organizacao-digital"),
            ("Criação Filhas", "criacao-filhas"),
            ("Finanças", "financas"),
            ("Saúde", "saude"),
            ("Santuário", "santuario"),
            # Case mixture
            ("Mirror Mind", "mirror-mind"),
            ("MIRROR-MIND", "mirror-mind"),
            # Espaços e underscores
            ("mirror mind", "mirror-mind"),
            ("mirror_mind", "mirror-mind"),
            ("mirror   mind", "mirror-mind"),
            # Extensão .yaml
            ("santuario.yaml", "santuario"),
            ("Saúde.yaml", "saude"),
            # Edge cases
            ("", None),
            (None, None),
            ("   ", None),
            ("null", None),
            ("None", None),
            (123, None),  # não-string
            # Hífens múltiplos
            ("mirror--mind", "mirror-mind"),
            ("-mirror-mind-", "mirror-mind"),
        ],
    )
    def test_normalization(self, raw, expected):
        assert normalize_travessia_slug(raw) == expected


class TestResolveTravessia:
    def test_valid_without_restriction(self):
        assert resolve_travessia("mirror-mind") == "mirror-mind"

    def test_normalizes_even_without_restriction(self):
        assert resolve_travessia("Mirror Mind") == "mirror-mind"
        assert resolve_travessia("Finanças") == "financas"

    def test_valid_slug_in_restriction_set(self):
        valid = {"mirror-mind", "ia-fronteira", "financas"}
        assert resolve_travessia("Mirror Mind", valid) == "mirror-mind"
        assert resolve_travessia("Finanças", valid) == "financas"

    def test_invalid_slug_returns_none_with_restriction(self):
        valid = {"mirror-mind", "ia-fronteira"}
        assert resolve_travessia("personal-os", valid) is None
        assert resolve_travessia("invalid-slug", valid) is None

    def test_none_input_returns_none(self):
        assert resolve_travessia(None, {"mirror-mind"}) is None
        assert resolve_travessia("", {"mirror-mind"}) is None

    def test_empty_valid_set_treats_all_as_invalid(self):
        # Um set vazio explícito rejeita tudo; None permite tudo
        assert resolve_travessia("mirror-mind", set()) is None
        assert resolve_travessia("mirror-mind", None) == "mirror-mind"
